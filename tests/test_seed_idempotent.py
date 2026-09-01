"""Seed idempotency and safety-gate tests — all against in-memory fakes.

Phase 2 exit criteria under test:
- rerun of the seeders performs zero writes (no duplicate issues, commits,
  pushes, PRs, or repo mutations);
- the seeder/resetter refuse any project key other than the scenario's;
- reset only deletes labeled issues, only deletes a GitHub repo carrying
  the seed marker, and only wipes inside a validated sandbox.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from groundtruth.adapters.github import GitHubError
from groundtruth.config import Settings
from groundtruth.contracts.ledger import ApprovalRef
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.safety import workspace as workspace_module
from groundtruth.safety.workspace import SANDBOX_SENTINEL
from groundtruth.seed.reset import Resetter
from groundtruth.seed.seed_git import REPO_MARKER_DESCRIPTION, GitSeeder
from groundtruth.seed.seed_jira import (
    JiraSeeder,
    SeedError,
    load_scenario,
    validate_against_settings,
)

SEED_LABEL = "groundtruth-seed"


# -- fakes -------------------------------------------------------------------


class FakeJira:
    """In-memory board implementing exactly the surface the seeders call."""

    def __init__(self, project_key: str = "AUTO") -> None:
        self.project_key = project_key
        self._issues: dict[str, dict[str, Any]] = {}
        self._comments: dict[str, list[str]] = {}
        self._next = 0
        self.created: list[str] = []
        self.transitions: list[tuple[str, str]] = []
        self.comments_added: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def add_issue(self, key: str, summary: str, labels: list[str]) -> None:
        self._issues[key] = {
            "key": key,
            "fields": {
                "summary": summary,
                "labels": list(labels),
                "status": {"name": "To Do"},
            },
        }
        self._comments.setdefault(key, [])

    def drop_issue(self, key: str) -> None:
        del self._issues[key]
        del self._comments[key]

    def search(self, jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        assert f'project = "{self.project_key}"' in jql
        assert f'labels = "{SEED_LABEL}"' in jql
        return [dict(issue) for issue in self._issues.values()
                if SEED_LABEL in issue["fields"]["labels"]]

    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        self._next += 1
        key = f"{self.project_key}-{self._next}"
        self.add_issue(key, fields["summary"], fields.get("labels", []))
        self.created.append(key)
        return self._issues[key]

    def get_issue(self, key: str, fields: list[str] | None = None) -> dict[str, Any]:
        return self._issues[key]

    def transition_to(self, key: str, target_status: str) -> dict[str, Any]:
        self.transitions.append((key, target_status))
        self._issues[key]["fields"]["status"] = {"name": target_status}
        return {}

    def get_comments(self, key: str) -> list[dict[str, Any]]:
        def adf(text: str) -> dict[str, Any]:
            return {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph",
                     "content": [{"type": "text", "text": text}]}
                ],
            }

        return [{"body": adf(t)} for t in self._comments[key]]

    def add_comment(self, key: str, text: str) -> dict[str, Any]:
        self.comments_added.append((key, text))
        self._comments[key].append(text)
        return {}

    def delete_issue(self, key: str) -> None:
        self.deleted.append(key)
        self.drop_issue(key)


class FakeGitHub:
    """In-memory GitHub repo + PRs implementing the client surface."""

    def __init__(
        self,
        slug: str = "owner/demo",
        exists: bool = False,
        description: str | None = None,
    ) -> None:
        self.slug = slug
        self._exists = exists
        self._description = description
        self._prs: dict[int, dict[str, Any]] = {}
        self._next_pr = 0
        self.repo_created = False
        self.repo_deleted = False
        self.description_sets: list[str] = []
        self.prs_created: list[str] = []
        self.prs_merged: list[int] = []

    def repo_get(self) -> dict[str, Any] | None:
        if not self._exists:
            return None
        return {"full_name": self.slug, "description": self._description}

    def repo_create(self, private: bool = True) -> None:
        if self._exists:
            raise GitHubError("GraphQL: Name already exists on this account")
        self._exists = True
        self.repo_created = True

    def repo_set_description(self, description: str) -> None:
        self._exists = True
        self._description = description
        self.description_sets.append(description)

    def repo_delete(self) -> None:
        self.repo_deleted = True
        self._exists = False

    def pr_list(self, state: str = "open") -> list[dict[str, Any]]:
        wanted = state.upper()
        return [dict(pr) for pr in self._prs.values()
                if wanted == "ALL" or pr["state"] == wanted]

    def pr_create(self, title: str, body: str, head: str, base: str) -> str:
        self._next_pr += 1
        number = self._next_pr
        self._prs[number] = {
            "number": number,
            "state": "OPEN",
            "title": title,
            "headRefName": head,
            "baseRefName": base,
        }
        self.prs_created.append(head)
        return f"https://github.com/{self.slug}/pull/{number}"

    def pr_merge(self, number: int, method: str = "squash") -> None:
        self.prs_merged.append(number)
        self._prs[number]["state"] = "MERGED"
        self._prs[number]["mergedAt"] = "2026-08-20T00:00:00Z"


class FakeGuard:
    """Mini in-memory git (plus remote) interpreting the seeder's commands."""

    def __init__(self, sandbox_path: Path, workspace_id: str = "test-workspace") -> None:
        self.sandbox_path = sandbox_path
        self.workspace_id = workspace_id
        self.allowed_remote = "owner/demo"
        self.branches: dict[str, str | None] = {}
        self.remote_branches: dict[str, str] = {}
        self.commits: dict[str, dict[str, Any]] = {}
        self.origin_url = ""
        self._head = ""
        self.log: list[list[str]] = []

    def run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.log.append(list(args))
        stdout, code = self._exec(args)
        if code != 0 and check:
            raise subprocess.CalledProcessError(code, args, stderr="fake git failure")
        return subprocess.CompletedProcess(
            args, code, stdout=stdout,
            stderr="" if code == 0 else "fake git failure",
        )

    def _exec(self, args: list[str]) -> tuple[str, int]:
        cmd = args[1] if len(args) > 1 else ""
        rest = args[2:]
        refs = [a for a in rest if not a.startswith("-")]

        if cmd == "init":
            branch = rest[rest.index("-b") + 1]
            self.branches.setdefault(branch, None)
            self._head = branch
            (self.sandbox_path / ".git").mkdir(parents=True, exist_ok=True)
            return "", 0
        if cmd == "add":
            for rel in refs:
                assert (self.sandbox_path / rel).exists(), f"git add missing path {rel}"
            return "", 0
        if cmd == "commit":
            message = rest[rest.index("-m") + 1]
            parent = self.branches.get(self._head)
            sha = hashlib.sha256(
                f"{parent}|{self._head}|{message}".encode()
            ).hexdigest()[:12]
            self.commits[sha] = {"message": message, "parent": parent}
            self.branches[self._head] = sha
            return "", 0
        if cmd == "checkout":
            if rest and rest[0] == "-b":
                name, base = rest[1], rest[2]
                self.branches[name] = self.branches.get(base)
                self._head = name
            else:
                self._head = refs[0]
            return "", 0
        if cmd == "rev-parse":
            ref = refs[0] if refs else ""
            resolved = self._head if ref == "HEAD" else ref
            if "--verify" in rest and resolved not in self.branches:
                return "", 128
            return (self.branches.get(resolved) or ""), 0
        if cmd == "push":
            branch = refs[1]
            self.remote_branches[branch] = self.branches[branch] or ""
            return "", 0
        if cmd == "ls-remote":
            branch = refs[1] if len(refs) > 1 else ""
            sha = self.remote_branches.get(branch)
            return (f"{sha}\trefs/heads/{branch}" if sha else ""), 0
        if cmd == "remote":
            if rest[0] == "get-url":
                return (self.origin_url, 0) if self.origin_url else ("", 128)
            self.origin_url = rest[2]
            return "", 0
        raise AssertionError(f"FakeGuard cannot execute: {args}")


# -- helpers -------------------------------------------------------------------


def _approval() -> ApprovalRef:
    return ApprovalRef(
        changeset_hash="a" * 16,
        approved_by="tester",
        approved_at=datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc),
    )


def _manifest_tickets(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "hint": t["hint"],
            "key": f"AUTO-{i}",
            "summary": t["summary"],
            "status": t.get("status", ""),
            "control": bool(t.get("control")),
            "branch": t.get("branch"),
        }
        for i, t in enumerate(scenario["tickets"], start=1)
    ]


def _ledger_entries(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sandbox(tmp_path: Path, workspace_id: str = "test-workspace") -> Path:
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / SANDBOX_SENTINEL).write_text(workspace_id, encoding="utf-8")
    return sandbox


# -- JiraSeeder ----------------------------------------------------------------


class TestJiraSeederIdempotency:
    def test_first_run_creates_every_ticket_once(self) -> None:
        scenario = load_scenario()
        fake = FakeJira()
        seeder = JiraSeeder(Settings(jira_project_key="AUTO"), fake, scenario)

        assert len(seeder.plan()) == len(scenario["tickets"])

        manifest = seeder.run(approval=_approval())

        assert len(manifest) == len(scenario["tickets"])
        assert fake.created == [f"AUTO-{i}" for i in range(1, 10)]
        assert [t["key"] for t in manifest] == fake.created
        # every ticket converged to its scenario status (fake starts at To Do)
        assert len(fake.transitions) == len(scenario["tickets"])
        for ticket, entry in zip(scenario["tickets"], manifest):
            assert fake._issues[entry["key"]]["fields"]["status"]["name"] == ticket["status"]
        # exactly one seeded comment exists (dup-2 carries it)
        assert len(fake.comments_added) == 1
        assert fake.comments_added[0][0] == "AUTO-6"
        assert seeder.plan() == []

    def test_rerun_creates_zero_duplicates(self) -> None:
        scenario = load_scenario()
        fake = FakeJira()
        seeder = JiraSeeder(Settings(jira_project_key="AUTO"), fake, scenario)

        first = seeder.run()
        created_before = len(fake.created)
        transitions_before = len(fake.transitions)
        comments_before = len(fake.comments_added)

        second = seeder.run()

        assert len(fake.created) == created_before
        assert len(fake.transitions) == transitions_before
        assert len(fake.comments_added) == comments_before
        assert [t["key"] for t in second] == [t["key"] for t in first]

    def test_rerun_recreates_only_missing_tickets(self) -> None:
        scenario = load_scenario()
        fake = FakeJira()
        seeder = JiraSeeder(Settings(jira_project_key="AUTO"), fake, scenario)
        first = seeder.run()
        first_keys = {t["hint"]: t["key"] for t in first}
        fake.drop_issue("AUTO-1")
        fake.drop_issue("AUTO-4")

        second = seeder.run()
        second_keys = {t["hint"]: t["key"] for t in second}

        # only the two dropped hints were recreated; recreated tickets get
        # fresh server-assigned keys, everything else is untouched
        assert len(fake.created) == len(scenario["tickets"]) + 2
        assert second_keys["stale-progress"] != first_keys["stale-progress"]
        assert second_keys["done-no-binding"] != first_keys["done-no-binding"]
        for hint, key in first_keys.items():
            if hint not in ("stale-progress", "done-no-binding"):
                assert second_keys[hint] == key
        assert len(second) == len(scenario["tickets"])

    def test_comment_dedup_ignores_whitespace(self) -> None:
        scenario = load_scenario()
        fake = FakeJira()
        seeder = JiraSeeder(Settings(jira_project_key="AUTO"), fake, scenario)
        seeder.run()
        key = "AUTO-6"
        fake._comments[key] = [
            "  Possibly related to the other report timeout ticket.  "
        ]

        seeder.run()

        assert len(fake.comments_added) == 1


class TestProjectKeyGate:
    def test_missing_project_key_refused(self) -> None:
        scenario = load_scenario()
        with pytest.raises(SeedError, match="not configured"):
            validate_against_settings(Settings(jira_project_key=""), scenario)

    def test_wrong_project_key_refused(self) -> None:
        scenario = load_scenario()
        with pytest.raises(SeedError, match="Refusing"):
            validate_against_settings(Settings(jira_project_key="PROD"), scenario)

    def test_matching_project_key_accepted(self) -> None:
        scenario = load_scenario()
        validate_against_settings(Settings(jira_project_key="AUTO"), scenario)


# -- GitSeeder -----------------------------------------------------------------


class TestGitSeederIdempotency:
    def test_first_run_creates_repo_branches_and_prs(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        guard = FakeGuard(tmp_path / "sandbox")
        github = FakeGitHub()
        seeder = GitSeeder(Settings(), guard, scenario, github=github)

        result = seeder.run(_manifest_tickets(scenario), approval=_approval())

        branch_tickets = [t for t in scenario["tickets"] if t.get("branch")]
        assert len(branch_tickets) == 4
        assert result["repo_initialized"] is True
        assert len(result["branches"]) == 4
        assert all(b["created"] for b in result["branches"])
        assert all(b["pushed"] for b in result["branches"])
        # base branch holds exactly the unreferenced commit (a root commit)
        assert result["base_tip"] == guard.branches["main"]
        assert guard.commits[result["base_tip"]]["parent"] is None
        # exactly one PR, for merged-open (ticket 2), created and merged
        assert github.prs_created == ["feature/AUTO-2"]
        assert github.prs_merged == [1]
        assert github.repo_created is True
        assert github.description_sets == [REPO_MARKER_DESCRIPTION]

    def test_rerun_performs_zero_writes(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        guard = FakeGuard(tmp_path / "sandbox")
        github = FakeGitHub()
        seeder = GitSeeder(Settings(), guard, scenario, github=github)
        first = seeder.run(_manifest_tickets(scenario))
        tips_before = dict(guard.branches)
        remote_before = dict(guard.remote_branches)
        github_state = (
            github.prs_created[:],
            github.prs_merged[:],
            github.repo_created,
            github.description_sets[:],
        )
        guard.log.clear()

        second = seeder.run(_manifest_tickets(scenario))

        write_verbs = {"init", "add", "commit", "push", "checkout"}
        writes = [a for a in guard.log if len(a) > 1 and a[1] in write_verbs]
        assert writes == []
        assert (
            github.prs_created,
            github.prs_merged,
            github.repo_created,
            github.description_sets,
        ) == github_state
        assert guard.branches == tips_before
        assert guard.remote_branches == remote_before
        assert second["repo_initialized"] is False
        assert all(not b["created"] for b in second["branches"])
        assert all(b["pushed"] for b in second["branches"])
        assert second["branches"][1]["pr"]["state"] == "MERGED"
        assert second["base_tip"] == first["base_tip"]

    def test_push_required_without_github_client_refused(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        guard = FakeGuard(tmp_path / "sandbox")
        seeder = GitSeeder(Settings(), guard, scenario, github=None)

        with pytest.raises(SeedError, match="no GitHub client"):
            seeder.run(_manifest_tickets(scenario))

    def test_unknown_commit_reference_refused(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        guard = FakeGuard(tmp_path / "sandbox")
        scenario["tickets"][0]["branch"]["commits"] = ["c_does_not_exist"]
        seeder = GitSeeder(Settings(), guard, scenario, github=FakeGitHub())

        with pytest.raises(SeedError, match="unknown commit id"):
            seeder.run(_manifest_tickets(scenario))

    def test_commit_referencing_unknown_file_block_refused(
        self, tmp_path: Path
    ) -> None:
        scenario = load_scenario()
        guard = FakeGuard(tmp_path / "sandbox")
        scenario["commits"][0]["files"] = {"app.py": "no_such_block"}
        seeder = GitSeeder(Settings(), guard, scenario, github=FakeGitHub())

        with pytest.raises(SeedError, match="unknown file block"):
            seeder.run(_manifest_tickets(scenario))

    def test_plan_reports_branch_state(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        guard = FakeGuard(tmp_path / "sandbox")
        seeder = GitSeeder(Settings(), guard, scenario, github=FakeGitHub())

        plan = seeder.plan(_manifest_tickets(scenario))

        assert plan["repo_initialized"] is False
        assert plan["base_branch"] == "main"
        assert len(plan["branches"]) == 4
        assert all(not b["exists"] for b in plan["branches"])
        pr_branches = [b for b in plan["branches"] if b["pr"]]
        assert [b["key"] for b in pr_branches] == ["AUTO-2"]


# -- Resetter ------------------------------------------------------------------


class TestResetter:
    @pytest.fixture(autouse=True)
    def _allow_tmp_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # reset wipes the sandbox, which must validate against ALLOWED_ROOT;
        # point it at tmp_path so the hermetic test sandbox qualifies.
        monkeypatch.setattr(workspace_module, "ALLOWED_ROOT", tmp_path)

    def _settings(self) -> Settings:
        return Settings(jira_project_key="AUTO")

    def test_deletes_only_labeled_issues(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        fake = FakeJira()
        JiraSeeder(self._settings(), fake, scenario).run()
        fake.add_issue("AUTO-99", "Untouched operators ticket", [])
        sandbox = _sandbox(tmp_path)
        resetter = Resetter(self._settings(), fake, FakeGuard(sandbox), scenario)

        plan = resetter.plan()
        planned_keys = [i["key"] for i in plan["jira_issues"]]
        assert "AUTO-99" not in planned_keys
        assert len(planned_keys) == len(scenario["tickets"])
        assert plan["github_repo"] == "absent"
        assert plan["local_repo"] is False

        result = resetter.run(approval=_approval())

        assert sorted(result["jira_deleted"]) == sorted(planned_keys)
        assert "AUTO-99" in fake._issues
        assert result["github_repo"] == "skipped"

    def test_refuses_foreign_github_repo(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        github = FakeGitHub(exists=True, description="someone else's repo")
        sandbox = _sandbox(tmp_path)
        ledger_path = tmp_path / "ledger.jsonl"
        resetter = Resetter(
            self._settings(),
            FakeJira(),
            FakeGuard(sandbox),
            scenario,
            ledger=LedgerWriter(ledger_path),
            github=github,
        )

        result = resetter.run(approval=_approval())

        assert result["github_repo"] == "foreign"
        assert github.repo_deleted is False
        entries = _ledger_entries(ledger_path)
        refused = [e for e in entries if e["action"] == "reset.github.repo_delete"]
        assert len(refused) == 1
        assert refused[0]["outcome"] == "refused"
        assert "marker" in (refused[0]["error"] or "")

    def test_deletes_marked_github_repo(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        github = FakeGitHub(exists=True, description=REPO_MARKER_DESCRIPTION)
        sandbox = _sandbox(tmp_path)
        resetter = Resetter(
            self._settings(), FakeJira(), FakeGuard(sandbox), scenario, github=github
        )

        result = resetter.run()

        assert result["github_repo"] == "deleted"
        assert github.repo_deleted is True

    def test_absent_repo_reported_without_calls(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        github = FakeGitHub(exists=False)
        sandbox = _sandbox(tmp_path)
        resetter = Resetter(
            self._settings(), FakeJira(), FakeGuard(sandbox), scenario, github=github
        )

        result = resetter.run()

        assert result["github_repo"] == "absent"
        assert github.repo_deleted is False
        assert github.repo_created is False

    def test_wipes_local_sandbox_preserving_sentinel(
        self, tmp_path: Path
    ) -> None:
        scenario = load_scenario()
        sandbox = _sandbox(tmp_path)
        (sandbox / "app.py").write_text("x", encoding="utf-8")
        git_dir = sandbox / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
        resetter = Resetter(
            self._settings(), FakeJira(), FakeGuard(sandbox), scenario
        )

        result = resetter.run()

        assert result["local_entries_removed"] == 2
        assert (sandbox / SANDBOX_SENTINEL).exists()
        assert not (sandbox / "app.py").exists()
        assert not git_dir.exists()

    def test_refuses_wrong_project_key(self, tmp_path: Path) -> None:
        scenario = load_scenario()
        fake = FakeJira()
        JiraSeeder(self._settings(), fake, scenario).run()
        sandbox = _sandbox(tmp_path)
        resetter = Resetter(
            Settings(jira_project_key="PROD"), fake, FakeGuard(sandbox), scenario
        )

        with pytest.raises(SeedError, match="Refusing"):
            resetter.run()

        assert fake.deleted == []
