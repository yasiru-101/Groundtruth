"""Seed the sandbox git repo (and its GitHub remote) from scenario.yaml.

The repo lives directly in the validated sandbox: GitGuard pins GIT_DIR and
GIT_WORK_TREE to the sandbox root, so the sentinel file simply stays
untracked (the seeder only ever stages explicit file paths).

Determinism: every commit is authored by the scenario identity with both
GIT_AUTHOR_DATE and GIT_COMMITTER_DATE pinned to ``epoch - days_before``,
core.autocrlf and commit.gpgsign are disabled via GIT_CONFIG_* env vars
(neither command strings nor config files are touched), so the seeded SHAs
are identical on every machine.

Idempotency: an initialized repo and existing branch names are detected and
skipped — a rerun performs zero writes. The remote repo, pushes, PRs, and
merges are likewise skipped when already present.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from typing import Any

from groundtruth.adapters.github import GitHubClient, GitHubError
from groundtruth.config import Settings
from groundtruth.contracts.ledger import ApprovalRef, LedgerMode, LedgerOutcome
from groundtruth.ids import content_hash
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.safety.git_guard import GitGuard
from groundtruth.safety.workspace import ensure_sandbox
from groundtruth.seed.seed_jira import SeedError

REPO_MARKER_DESCRIPTION = "groundtruth-seeded demo repo"


class GitSeeder:
    def __init__(
        self,
        settings: Settings,
        guard: GitGuard,
        scenario: dict[str, Any],
        ledger: LedgerWriter | None = None,
        github: GitHubClient | None = None,
    ) -> None:
        self._settings = settings
        self._guard = guard
        self._scenario = scenario
        self._ledger = ledger
        self._github = github
        self._repo = guard.sandbox_path
        self._author = scenario["git"]["author"]
        self._base_branch = scenario["git"].get("base_branch", "main")
        self._epoch = datetime.fromisoformat(scenario["epoch"])
        self._commits_by_id = {c["id"]: c for c in scenario["commits"]}

    # -- environment ---------------------------------------------------------

    def _base_env(self) -> dict[str, str]:
        env: dict[str, str] = {
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "core.autocrlf",
            "GIT_CONFIG_VALUE_0": "false",
            "GIT_CONFIG_KEY_1": "commit.gpgsign",
            "GIT_CONFIG_VALUE_1": "false",
            "GIT_AUTHOR_NAME": self._author["name"],
            "GIT_AUTHOR_EMAIL": self._author["email"],
            "GIT_COMMITTER_NAME": self._author["name"],
            "GIT_COMMITTER_EMAIL": self._author["email"],
        }
        return env

    def _commit_env(self, commit: dict[str, Any]) -> dict[str, str]:
        when = (self._epoch - timedelta(days=int(commit["days_before"]))).isoformat()
        env = self._base_env()
        env["GIT_AUTHOR_DATE"] = when
        env["GIT_COMMITTER_DATE"] = when
        return env

    # -- git plumbing ---------------------------------------------------------

    def _run(
        self,
        args: list[str],
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self._guard.run(args, check=True, env_extra=env_extra)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()[:2000]
            raise SeedError(
                f"git {' '.join(args[:4])} failed (exit {exc.returncode}): {stderr}"
            ) from exc

    def _probe(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return self._guard.run(args, check=False, env_extra=self._base_env())

    def repo_initialized(self) -> bool:
        return (self._repo / ".git").exists()

    def _branch_exists(self, name: str) -> bool:
        return self._probe(["git", "rev-parse", "--verify", name]).returncode == 0

    def _tip_sha(self, rev: str) -> str:
        return self._probe(["git", "rev-parse", rev]).stdout.strip()

    def _write_files(self, files: dict[str, str]) -> list[str]:
        rel_paths: list[str] = []
        for rel, block_name in files.items():
            if block_name not in self._scenario["files"]:
                raise SeedError(
                    f"Commit references unknown file block {block_name!r} "
                    f"(writing {rel!r})."
                )
            path = self._repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                self._scenario["files"][block_name], encoding="utf-8", newline="\n"
            )
            rel_paths.append(rel)
        return rel_paths

    def _make_commit(self, commit: dict[str, Any]) -> str:
        env = self._commit_env(commit)
        rel_paths = self._write_files(commit["files"])
        self._run(["git", "add", *rel_paths], env_extra=env)
        self._run(["git", "commit", "-m", commit["message"]], env_extra=env)
        return self._tip_sha("HEAD")

    def _unreferenced_commits(self) -> list[dict[str, Any]]:
        referenced: set[str] = set()
        for ticket in self._scenario["tickets"]:
            branch = ticket.get("branch")
            if branch:
                referenced.update(branch.get("commits", []))
        return [c for c in self._scenario["commits"] if c["id"] not in referenced]

    # -- ledger ---------------------------------------------------------------

    def _ledger_append(self, action: str, subject: str, *, inputs: str = "",
                       approval: ApprovalRef | None = None) -> None:
        if self._ledger is None:
            return
        self._ledger.append(
            actor="seeder",
            action=action,
            mode=LedgerMode.APPLY,
            subject=subject,
            inputs_hash=inputs,
            outcome=LedgerOutcome.OK,
            approval=approval,
        )

    # -- remote ----------------------------------------------------------------

    def _remote_url(self) -> str:
        return f"https://github.com/{self._github.slug}.git"

    def _ensure_remote_repo(self, approval: ApprovalRef | None = None) -> None:
        repo = self._github.repo_get()
        if repo is None:
            try:
                self._github.repo_create(private=True)
                self._ledger_append(
                    "seed.github.repo_create",
                    self._github.slug,
                    inputs=content_hash(self._github.slug),
                    approval=approval,
                )
            except GitHubError as exc:
                if "already exists" not in str(exc).lower():
                    raise
        # The marker description lets reset prove the repo is ours before
        # it will consider deleting it.
        if repo is None or repo.get("description") != REPO_MARKER_DESCRIPTION:
            self._github.repo_set_description(REPO_MARKER_DESCRIPTION)

    def _set_origin(self) -> None:
        url = self._remote_url()
        probe = self._probe(["git", "remote", "get-url", "origin"])
        current = probe.stdout.strip() if probe.returncode == 0 else ""
        if probe.returncode != 0:
            self._run(["git", "remote", "add", "origin", url], env_extra=self._base_env())
        elif current != url:
            self._run(
                ["git", "remote", "set-url", "origin", url], env_extra=self._base_env()
            )

    def _remote_tip(self, branch: str) -> str:
        probe = self._probe(["git", "ls-remote", "origin", branch])
        if probe.returncode != 0:
            return ""
        output = probe.stdout.strip()
        return output.split()[0] if output else ""

    def _push(self, branch: str, approval: ApprovalRef | None = None) -> bool:
        local_tip = self._tip_sha(branch)
        if self._remote_tip(branch) == local_tip:
            return True
        try:
            self._run(["git", "push", "-u", "origin", branch], env_extra=self._base_env())
        except SeedError as exc:
            message = str(exc)
            hints = ("Authentication failed", "403", "could not read Username", "Permission")
            if any(h in message for h in hints):
                raise SeedError(
                    message
                    + " — git could not authenticate to GitHub. Run "
                    "'gh auth setup-git' once so git pushes via gh credentials."
                ) from exc
            raise
        self._ledger_append(
            "seed.git.push",
            branch,
            inputs=content_hash(branch, self._tip_sha(branch)),
            approval=approval,
        )
        return True

    def _pr_for_head(self, branch: str) -> dict[str, Any] | None:
        for pr in self._github.pr_list(state="all"):
            if pr.get("headRefName") == branch:
                return pr
        return None

    def _ensure_pr(
        self,
        ticket: dict[str, Any],
        branch: str,
        pr_spec: dict[str, Any],
        approval: ApprovalRef | None = None,
    ) -> dict[str, Any]:
        base = pr_spec.get("base", self._base_branch)
        pr = self._pr_for_head(branch)

        if pr is None:
            url = self._github.pr_create(
                title=ticket["summary"],
                body=f"Implements {ticket['summary']} ({ticket['key']}). "
                "Seeded by Groundtruth.",
                head=branch,
                base=base,
            )
            self._ledger_append(
                "seed.github.pr_create",
                url,
                inputs=content_hash(ticket["key"], branch, base),
                approval=approval,
            )
            number = int(url.rstrip("/").rsplit("/", 1)[-1])
            pr = {"number": number, "state": "OPEN", "headRefName": branch}
        else:
            number = int(pr["number"])

        merged = str(pr.get("state", "")).upper() == "MERGED" or bool(pr.get("mergedAt"))
        if not merged:
            self._github.pr_merge(number, method=pr_spec.get("merge", "squash"))
            self._ledger_append(
                "seed.github.pr_merge",
                str(number),
                inputs=content_hash(str(number), pr_spec.get("merge", "squash")),
                approval=approval,
            )
            pr["state"] = "MERGED"
        return pr

    # -- entry point -------------------------------------------------------------

    def plan(self, manifest_tickets: list[dict[str, Any]]) -> dict[str, Any]:
        branches = []
        for ticket in manifest_tickets:
            branch_spec = ticket.get("branch")
            if not branch_spec:
                continue
            branch = branch_spec["name_template"].format(key=ticket["key"])
            branches.append(
                {
                    "hint": ticket["hint"],
                    "key": ticket["key"],
                    "branch": branch,
                    "exists": self._branch_exists(branch),
                    "push": bool(branch_spec.get("push")),
                    "pr": bool(branch_spec.get("pr")),
                }
            )
        return {
            "repo_initialized": self.repo_initialized(),
            "base_branch": self._base_branch,
            "branches": branches,
        }

    def run(
        self,
        manifest_tickets: list[dict[str, Any]],
        approval: ApprovalRef | None = None,
    ) -> dict[str, Any]:
        ensure_sandbox(self._repo, self._guard.workspace_id)

        needs_remote = any(
            (t.get("branch") or {}).get("push") for t in manifest_tickets
        )
        if needs_remote and self._github is None:
            raise SeedError(
                "Scenario requests pushed branches but no GitHub client was "
                "provided (set GITHUB_REPO_OWNER / GITHUB_REPO_NAME)."
            )

        result: dict[str, Any] = {
            "base_branch": self._base_branch,
            "repo_initialized": False,
            "base_tip": None,
            "branches": [],
        }

        if not self.repo_initialized():
            self._run(
                ["git", "init", "-b", self._base_branch], env_extra=self._base_env()
            )
            self._ledger_append(
                "seed.git.init",
                str(self._repo),
                inputs=content_hash(str(self._repo), self._base_branch),
                approval=approval,
            )
            for commit in self._unreferenced_commits():
                sha = self._make_commit(commit)
                self._ledger_append(
                    "seed.git.commit",
                    sha,
                    inputs=content_hash(commit["id"], commit["message"]),
                    approval=approval,
                )
            result["repo_initialized"] = True
        result["base_tip"] = self._tip_sha(self._base_branch)

        if needs_remote:
            self._ensure_remote_repo(approval=approval)
            self._set_origin()
            self._push(self._base_branch, approval=approval)

        for ticket in manifest_tickets:
            branch_spec = ticket.get("branch")
            if not branch_spec:
                continue
            branch = branch_spec["name_template"].format(key=ticket["key"])
            entry: dict[str, Any] = {
                "hint": ticket["hint"],
                "key": ticket["key"],
                "branch": branch,
                "created": False,
                "pushed": False,
                "pr": None,
                "commits": [],
            }

            if not self._branch_exists(branch):
                self._run(
                    ["git", "checkout", "-b", branch, self._base_branch],
                    env_extra=self._base_env(),
                )
                self._ledger_append(
                    "seed.git.branch",
                    branch,
                    inputs=content_hash(branch, ticket["key"]),
                    approval=approval,
                )
                for commit_id in branch_spec.get("commits", []):
                    commit = self._commits_by_id.get(commit_id)
                    if commit is None:
                        raise SeedError(
                            f"Ticket {ticket['hint']!r} references unknown "
                            f"commit id {commit_id!r}."
                        )
                    sha = self._make_commit(commit)
                    entry["commits"].append({"id": commit_id, "sha": sha})
                    self._ledger_append(
                        "seed.git.commit",
                        sha,
                        inputs=content_hash(commit_id, commit["message"]),
                        approval=approval,
                    )
                entry["created"] = True

            if branch_spec.get("push"):
                entry["pushed"] = self._push(branch, approval=approval)

            pr_spec = branch_spec.get("pr")
            if pr_spec:
                entry["pr"] = self._ensure_pr(ticket, branch, pr_spec, approval)

            result["branches"].append(entry)

        return result
