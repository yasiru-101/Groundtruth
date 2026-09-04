"""Hermetic replay coverage for the complete Phase 5 pipeline."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

import groundtruth.agents.delivery as delivery_module
from groundtruth.adapters.base import Envelope, FixtureStore
from groundtruth.adapters.github import GitHubClient
from groundtruth.adapters.gitlog import GitLog
from groundtruth.adapters.jira import JiraClient, adf_text
from groundtruth.adapters.llm import LLMClient, PromptName
from groundtruth.agents.delivery import DeliveryAgent
from groundtruth.agents.intake import IntakeAgent
from groundtruth.agents.planner import PlannerAgent
from groundtruth.agents.reporting import ReportingAgent
from groundtruth.agents.steward import BoardSteward
from groundtruth.clock import FrozenClock
from groundtruth.config import RunMode, Settings
from groundtruth.contracts.delivery import AuthoredTests, RepairIteration
from groundtruth.contracts.ledger import ApprovalRef
from groundtruth.contracts.testrun import TestOutcome, TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import TraceLink
from groundtruth.ledger.reader import verify_chain
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.scoring import compute_score
from groundtruth.seed.seed_jira import JiraSeeder, build_manifest, load_scenario


AS_OF = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
NODE_ID = "tests/test_auto_1.py::test_delivers_feature"


class SeedJira:
    def __init__(self) -> None:
        self.issues: dict[str, dict[str, Any]] = {}
        self.comments: dict[str, list[str]] = {}
        self._next = 0

    def search(self, _jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        del fields
        return [
            issue
            for issue in self.issues.values()
            if "groundtruth-seed" in issue["fields"].get("labels", [])
        ]

    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        self._next += 1
        key = f"AUTO-{self._next}"
        issue = {
            "key": key,
            "fields": {
                **fields,
                "status": {"name": "To Do"},
                "components": [],
            },
        }
        self.issues[key] = issue
        self.comments[key] = []
        return issue

    def get_issue(self, key: str, fields: list[str] | None = None) -> dict[str, Any]:
        del fields
        return self.issues[key]

    def transition_to(self, key: str, target_status: str) -> dict[str, Any]:
        self.issues[key]["fields"]["status"] = {"name": target_status}
        return {}

    def get_comments(self, key: str) -> list[dict[str, Any]]:
        return [{"body": adf_text(text)} for text in self.comments[key]]

    def add_comment(self, key: str, text: str) -> dict[str, Any]:
        self.comments[key].append(text)
        return {}


class IntakeJira:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    def search(self, _jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        del fields
        return []

    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        key = f"AUTO-{10 + len(self.created)}"
        self.created.append({"key": key, "fields": fields})
        return {"key": key}

    def add_comment(self, key: str, text: str) -> dict[str, Any]:
        assert key == "AUTO-10"
        assert "Created by Groundtruth intake" in text
        return {}


class RecordingObserverGuard:
    allowed_remote = "acme/demo"

    def run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, env_extra
        if args == ["git", "branch", "--format=%(refname:short)"]:
            return _completed(
                args,
                "main\nfeature/AUTO-1\nfeature/AUTO-2\nfeature/AUTO-3\ngt-control/AUTO-8\n",
            )
        if args[:2] == ["git", "log"]:
            branch = args[2].split("..", 1)[-1]
            return _completed(args, _git_log(branch))
        raise AssertionError(f"unexpected recording git command: {args}")

    def run_gh(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, env_extra
        if args[:3] == ["gh", "pr", "list"]:
            return _completed(
                args,
                json.dumps(
                    [
                        {
                            "number": 2,
                            "state": "MERGED",
                            "headRefName": "feature/AUTO-2",
                            "baseRefName": "main",
                            "mergedAt": "2026-08-18T09:00:00+00:00",
                            "mergeCommit": {"oid": "merge-auto-2"},
                            "url": "https://github.com/acme/demo/pull/2",
                        }
                    ]
                ),
            )
        if args[:3] == ["gh", "api", "repos/acme/demo/commits/merge-auto-2/check-runs"]:
            return _completed(
                args,
                json.dumps(
                    {
                        "check_runs": [
                            {"status": "completed", "conclusion": "success", "name": "CI"}
                        ]
                    }
                ),
            )
        raise AssertionError(f"unexpected recording GitHub command: {args}")


class FailingObserverGuard:
    allowed_remote = ""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        self.calls += 1
        raise AssertionError("git was touched during replay")

    def run_gh(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        self.calls += 1
        raise AssertionError("GitHub was touched during replay")


class DeliveryGuard:
    def __init__(self) -> None:
        self.branches = {"main"}
        self.commands: list[list[str]] = []

    def run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, capture_output, env_extra
        self.commands.append(list(args))
        if args == ["git", "status", "--porcelain"]:
            return _completed(args)
        if args[:3] == ["git", "branch", "--list"]:
            branch = args[3]
            return _completed(args, f"{branch}\n" if branch in self.branches else "")
        if args[:2] == ["git", "checkout"]:
            if args[2] == "-b":
                self.branches.add(args[3])
            return _completed(args)
        if args == ["git", "diff", "--cached", "--quiet"]:
            return _completed(args, returncode=1)
        if args == ["git", "rev-parse", "HEAD"]:
            return _completed(args, "delivery-sha\n")
        return _completed(args)


class DeliveryGitHub:
    slug = "acme/demo"

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.pull_requests: list[dict[str, Any]] = []

    def pr_list(self, state: str = "open") -> list[dict[str, Any]]:
        del state
        return list(self.pull_requests)

    def pr_create(self, **kwargs: Any) -> str:
        self.created.append(kwargs)
        url = "https://github.com/acme/demo/pull/100"
        self.pull_requests.append({"headRefName": kwargs["head"], "url": url})
        return url


def _completed(
    args: list[str], stdout: str = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")


def _git_log(branch: str) -> str:
    records = {
        "feature/AUTO-1": ("stale-auto-1", "2026-08-20T09:00:00+00:00", "wip: pagination"),
        "feature/AUTO-2": ("merged-auto-2", "2026-08-28T09:00:00+00:00", "feat: csv export"),
        "feature/AUTO-3": ("orphan-auto-3", "2026-08-27T09:00:00+00:00", "wip: SSO registry"),
        "gt-control/AUTO-8": ("control-auto-8", "2026-08-31T09:00:00+00:00", "chore: dependencies"),
    }
    sha, timestamp, subject = records[branch]
    return "\x1f".join(
        [
            sha,
            timestamp,
            timestamp,
            "Groundtruth Seeder",
            "seeder@groundtruth.local",
            subject,
            "main-base",
        ]
    ) + "\x1e"


def _run(status: TestOutcomeStatus, message: str = "") -> TestRunResult:
    return TestRunResult(
        run_id="e2e-test-run",
        exit_code=0 if status is TestOutcomeStatus.PASSED else 1,
        collected_node_ids={NODE_ID},
        tests={NODE_ID: TestOutcome(node_id=NODE_ID, status=status, message=message)},
    )


def _author_tests(
    _llm: object,
    _ticket_key: str,
    _summary: str,
    _description: str,
    _criteria: list[object],
    workspace: Path,
    *,
    existing_tests: list[str] | None = None,
) -> AuthoredTests:
    del existing_tests
    content = "def test_delivers_feature():\n    assert False\n"
    path = workspace / "tests" / "test_auto_1.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return AuthoredTests(
        test_file="tests/test_auto_1.py",
        content=content,
        bindings=[
            TraceLink(
                ac_id="AUTO-1#1",
                test_node_id=NODE_ID,
                bound_at=AS_OF,
                test_file_hash="e2e-test-hash",
            )
        ],
    )


def _repair_loop(*args: object, workspace: Path, **kwargs: object) -> list[RepairIteration]:
    del args, kwargs
    source = workspace / "src" / "feature.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8", newline="\n")
    return [
        RepairIteration(
            iteration=1,
            phase="implement",
            files_changed=["src/feature.py"],
            red_gate_valid=True,
            green=True,
        )
    ]


def test_replay_pipeline_from_seed_through_score(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        run_mode=RunMode.REPLAY,
        jira_base_url="https://jira.example",
        jira_email="e2e@example.test",
        jira_api_token="e2e-token",
        jira_project_key="AUTO",
        github_repo_owner="acme",
        github_repo_name="demo",
        llm_api_key="key",
        llm_model="model",
        llm_base_url="https://llm.example",
        workspace_dir=tmp_path / "workspace",
        artifacts_dir=tmp_path / "artifacts",
        fixtures_dir=tmp_path / "fixtures",
    )
    settings.workspace_dir.mkdir(parents=True)
    notes_path = tmp_path / "intake.md"
    notes_text = "Add an audit export for managers."
    notes_path.write_text(notes_text, encoding="utf-8", newline="\n")

    scenario = load_scenario()
    seed_jira = SeedJira()
    seeded = JiraSeeder(settings, seed_jira, scenario).run()
    seed_run = settings.artifacts_dir / "run_e2e_seed"
    seed_run.mkdir(parents=True)
    seed_manifest = build_manifest(scenario, "AUTO", seeded, "e2e-seed")
    (seed_run / "manifest.json").write_text(
        json.dumps(seed_manifest), encoding="utf-8", newline="\n"
    )
    assert len(seeded) == 9
    seed_jira.issues["AUTO-1"]["fields"]["description"] = adf_text(
        "Given: a search request\n"
        "When: the feature is delivered\n"
        "Then: the requested behavior is available"
    )

    snapshot = json.loads(json.dumps(list(seed_jira.issues.values())))
    record_envelope = Envelope(
        RunMode.RECORD,
        FixtureStore(settings.fixtures_dir),
        clock=FrozenClock(AS_OF),
    )

    def jira_response(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rest/api/3/search/jql":
            return httpx.Response(200, json={"issues": snapshot})
        if request.method == "GET" and request.url.path.endswith("/changelog"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "created": "2026-08-18T09:00:00+00:00",
                            "items": [{"field": "status"}],
                        }
                    ],
                    "total": 1,
                },
            )
        raise AssertionError(f"unexpected recording Jira request: {request.method} {request.url}")

    recording_guard = RecordingObserverGuard()
    record_steward = BoardSteward(
        settings=settings,
        envelope=record_envelope,
        jira=JiraClient(
            settings,
            record_envelope,
            client=httpx.Client(
                base_url=settings.jira_base_url,
                transport=httpx.MockTransport(jira_response),
            ),
        ),
        gitlog=GitLog(record_envelope, recording_guard),
        github=GitHubClient(settings, record_envelope, recording_guard),
    )
    record_steward.audit()

    intake_response = {
        "tickets": [
            {
                "summary": "Add an audit export for managers",
                "description": "Managers need a reusable audit export.",
                "acceptance_criteria": [
                    {
                        "given": "an auditor has completed a board review",
                        "when": "they export the findings",
                        "then": "a manager-readable export is available",
                    }
                ],
                "points": 3,
                "components": ["reports"],
                "depends_on": [],
            }
        ]
    }
    LLMClient(
        settings,
        record_envelope,
        client=httpx.Client(
            base_url=settings.llm_base_url,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": json.dumps(intake_response)}}]},
                )
            ),
        ),
    ).complete(PromptName.INTAKE_DECOMPOSE, {"doc_id": str(notes_path), "text": notes_text})
    assert FixtureStore(settings.fixtures_dir).keys()

    forbidden_requests: list[str] = []

    def forbid_network(request: httpx.Request) -> httpx.Response:
        forbidden_requests.append(f"{request.method} {request.url}")
        raise AssertionError("network was touched during replay")

    replay_envelope = Envelope(RunMode.REPLAY, FixtureStore(settings.fixtures_dir))
    replay_guard = FailingObserverGuard()
    replay_jira = JiraClient(
        settings,
        replay_envelope,
        client=httpx.Client(
            base_url=settings.jira_base_url,
            transport=httpx.MockTransport(forbid_network),
        ),
    )
    replay_steward = BoardSteward(
        settings=settings,
        envelope=replay_envelope,
        jira=replay_jira,
        gitlog=GitLog(replay_envelope, replay_guard),
        github=GitHubClient(settings, replay_envelope, replay_guard),
        ledger=LedgerWriter(settings.artifacts_dir / "run_e2e_audit" / "ledger.jsonl"),
    )
    audit = replay_steward.audit()
    assert audit.board.project_key == "AUTO"
    assert audit.discrepancies

    replay_llm = LLMClient(
        settings,
        replay_envelope,
        client=httpx.Client(
            base_url=settings.llm_base_url,
            transport=httpx.MockTransport(forbid_network),
        ),
    )
    intake = IntakeAgent(
        settings,
        IntakeJira(),
        replay_llm,
        steward=replay_steward,
        ledger=LedgerWriter(settings.artifacts_dir / "run_e2e_intake" / "ledger.jsonl"),
        clock=audit.clock,
    )
    changeset = intake.propose(notes_path)
    created = intake.apply(
        changeset,
        ApprovalRef(
            changeset_hash=changeset.compute_hash(),
            approved_by="e2e-test",
            approved_at=AS_OF,
        ),
    )
    assert [story.jira_key for story in created] == ["AUTO-10"]

    plan = PlannerAgent(
        audit.board,
        audit.repo,
        audit.clock,
        intake_state_path=settings.artifacts_dir / "intake_state.json",
    ).build_plan()
    assert plan.project_key == "AUTO"

    delivery_runs = iter(
        [
            _run(TestOutcomeStatus.FAILED, "AssertionError"),
            _run(TestOutcomeStatus.PASSED),
            _run(TestOutcomeStatus.PASSED),
        ]
    )
    monkeypatch.setattr(delivery_module, "author_tests", _author_tests)
    monkeypatch.setattr(delivery_module, "repair_loop", _repair_loop)
    monkeypatch.setattr(
        delivery_module,
        "run_tests",
        lambda **_: next(delivery_runs),
    )
    delivery_dir = settings.artifacts_dir / "run_e2e_deliver"
    delivery_github = DeliveryGitHub()
    delivery = DeliveryAgent(
        settings,
        seed_jira,
        object(),
        DeliveryGuard(),
        delivery_github,
        ledger=LedgerWriter(delivery_dir / "ledger.jsonl"),
    )
    result = delivery.deliver("AUTO-1", delivery_dir)
    assert result.green
    assert not result.draft
    assert result.pr_url == "https://github.com/acme/demo/pull/100"
    assert (settings.workspace_dir / "trace_manifest.json").read_bytes() == (
        delivery_dir / "trace_manifest.json"
    ).read_bytes()

    reused = delivery.deliver("AUTO-1", settings.artifacts_dir / "run_e2e_deliver_rerun")
    assert reused.green
    assert reused.pr_url == result.pr_url
    assert reused.notes == ["Existing delivery pull request reused."]
    assert len(delivery_github.created) == 1

    report_dir = settings.artifacts_dir / "run_e2e_report"
    report = ReportingAgent(
        settings=settings,
        steward=replay_steward,
        ledger=LedgerWriter(report_dir / "ledger.jsonl"),
    ).report(report_dir)
    assert report.prose_source == "template"
    assert (report_dir / "report.json").exists()
    assert (report_dir / "report.md").exists()

    ledgers = {
        path: verify_chain(path)
        for path in sorted(settings.artifacts_dir.glob("run_*/ledger.jsonl"))
    }
    assert all(ledgers.values())
    score = compute_score(
        audit.board,
        audit.repo,
        audit.clock,
        audit.policy,
        ledger_entries=[entry for entries in ledgers.values() for entry in entries],
    )
    assert 0.0 <= score.total <= 1.0
    assert forbidden_requests == []
    assert replay_guard.calls == 0
