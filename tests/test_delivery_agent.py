"""Direct orchestration tests for the guarded DeliveryAgent."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import groundtruth.agents.delivery as delivery_module
from groundtruth.agents.delivery import DeliveryAgent
from groundtruth.config import Settings
from groundtruth.contracts.delivery import AuthoredTests, DeliveryPhase, RepairIteration
from groundtruth.contracts.ledger import ApprovalRef
from groundtruth.contracts.testrun import TestOutcome, TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import TraceLink
from groundtruth.ledger.writer import LedgerWriter


NODE_ID = "tests/test_auto_1.py::test_delivers_feature"


class FakeJira:
    def __init__(self, labels: list[str] | None = None) -> None:
        self.labels = labels or []
        self.calls: list[tuple[str, list[str] | None]] = []

    def get_issue(self, key: str, fields: list[str] | None = None) -> dict[str, Any]:
        self.calls.append((key, fields))
        return {
            "key": key,
            "fields": {
                "summary": "Deliver feature",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Given: an enabled feature\n"
                                        "When: it is delivered\n"
                                        "Then: it is available"
                                    ),
                                }
                            ],
                        }
                    ],
                },
                "labels": self.labels,
            },
        }


class FakeGitHub:
    slug = "owner/repo"

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.pull_requests: list[dict[str, Any]] = []

    def pr_list(self, state: str = "open") -> list[dict[str, Any]]:
        return self.pull_requests

    def pr_create(self, **kwargs: Any) -> str:
        self.created.append(kwargs)
        return "https://github.com/owner/repo/pull/1"


class FakeGuard:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(args)
        if args == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args[:3] == ["git", "branch", "--list"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args == ["git", "diff", "--cached", "--quiet"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        if args == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def _run(
    outcomes: dict[str, tuple[TestOutcomeStatus, str]], *, exit_code: int
) -> TestRunResult:
    return TestRunResult(
        run_id="run-1",
        exit_code=exit_code,
        collected_node_ids=set(outcomes),
        tests={
            node: TestOutcome(node_id=node, status=status, message=message)
            for node, (status, message) in outcomes.items()
        },
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
    test_file = "tests/test_auto_1.py"
    content = "def test_delivers_feature():\n    assert False\n"
    target = workspace / test_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return AuthoredTests(
        test_file=test_file,
        content=content,
        bindings=[
            TraceLink(
                ac_id="AUTO-1#1",
                test_node_id=NODE_ID,
                bound_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                test_file_hash="test-hash",
            )
        ],
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        workspace_dir=tmp_path / "workspace",
        artifacts_dir=tmp_path / "artifacts",
    )


class TestDeliveryAgent:
    def test_delivers_green_pr_with_matching_trace_manifests(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        settings = _settings(tmp_path)
        settings.workspace_dir.mkdir(parents=True)
        guard = FakeGuard()
        github = FakeGitHub()
        calls: list[Path] = []
        runs = iter(
            [
                _run({NODE_ID: (TestOutcomeStatus.FAILED, "AssertionError")}, exit_code=1),
                _run(
                    {
                        NODE_ID: (TestOutcomeStatus.PASSED, ""),
                        "tests/test_existing.py::test_unrelated": (
                            TestOutcomeStatus.FAILED,
                            "AssertionError",
                        ),
                    },
                    exit_code=1,
                ),
            ]
        )

        def fake_run_tests(*, cwd: Path, report_path: Path) -> TestRunResult:
            assert cwd == settings.workspace_dir
            calls.append(report_path)
            return next(runs)

        def fake_repair_loop(*args: Any, workspace: Path, **kwargs: Any) -> list[RepairIteration]:
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

        monkeypatch.setattr(delivery_module, "author_tests", _author_tests)
        monkeypatch.setattr(delivery_module, "repair_loop", fake_repair_loop)
        monkeypatch.setattr(delivery_module, "run_tests", fake_run_tests)

        result = DeliveryAgent(settings, FakeJira(), object(), guard, github).deliver("AUTO-1")

        assert result.phase == DeliveryPhase.PR
        assert result.green
        assert not result.draft
        assert result.pr_url == "https://github.com/owner/repo/pull/1"
        assert result.head_sha == "abc123"
        assert result.unrelated_failures == ["tests/test_existing.py::test_unrelated"]
        assert len(calls) == 2
        assert github.created == [
            {
                "title": "AUTO-1: Deliver feature",
                "head": "deliver/auto-1",
                "base": "main",
                "draft": False,
                "body_file": Path(result.run_dir) / "pr_body.md",
            }
        ]
        assert (settings.workspace_dir / "trace_manifest.json").read_bytes() == (
            Path(result.run_dir) / "trace_manifest.json"
        ).read_bytes()
        persisted = json.loads((Path(result.run_dir) / "delivery_result.json").read_text())
        assert persisted["green"] is True
        assert (settings.workspace_dir / ".github" / "workflows" / "ci.yml").exists()
        assert ["git", "checkout", "-b", "deliver/auto-1"] in guard.commands
        assert ["git", "add", "tests/test_auto_1.py"] in guard.commands
        assert ["git", "add", "src/feature.py", "trace_manifest.json"] in guard.commands
        assert ["git", "add", ".github/workflows/ci.yml"] in guard.commands
        assert ["git", "push", "-u", "origin", "deliver/auto-1"] in guard.commands

    def test_refuses_control_group_before_git_operations(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        settings.workspace_dir.mkdir(parents=True)
        guard = FakeGuard()
        github = FakeGitHub()

        result = DeliveryAgent(
            settings, FakeJira(labels=["gt-control"]), object(), guard, github
        ).deliver("AUTO-1")

        assert result.phase == DeliveryPhase.BRANCH
        assert result.refusals == ["Control-group tickets cannot be delivered."]
        assert guard.commands == []
        assert github.created == []

    def test_refusal_ledger_includes_approval(self, tmp_path: Path) -> None:
        settings = _settings(tmp_path)
        settings.workspace_dir.mkdir(parents=True)
        ledger = LedgerWriter(tmp_path / "ledger.jsonl")
        approval = ApprovalRef(
            changeset_hash="changeset-hash",
            approved_by="operator",
            approved_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )

        DeliveryAgent(
            settings,
            FakeJira(labels=["gt-control"]),
            object(),
            FakeGuard(),
            FakeGitHub(),
            ledger=ledger,
            approval=approval,
        ).deliver("AUTO-1")

        entry = json.loads(ledger.ledger_path.read_text(encoding="utf-8"))
        assert entry["approval"]["changeset_hash"] == "changeset-hash"

    def test_invalid_red_gate_removes_authored_test_and_skips_pr(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        settings = _settings(tmp_path)
        settings.workspace_dir.mkdir(parents=True)
        guard = FakeGuard()
        github = FakeGitHub()

        monkeypatch.setattr(delivery_module, "author_tests", _author_tests)
        monkeypatch.setattr(
            delivery_module,
            "run_tests",
            lambda **_: _run({NODE_ID: (TestOutcomeStatus.PASSED, "")}, exit_code=0),
        )

        result = DeliveryAgent(settings, FakeJira(), object(), guard, github).deliver("AUTO-1")

        assert result.phase == DeliveryPhase.RED_GATE
        assert not result.red_gate.is_valid_red
        assert result.refusals == [
            "Red gate failed: every bound test must fail by assertion."
        ]
        assert not (settings.workspace_dir / "tests" / "test_auto_1.py").exists()
        assert github.created == []
        assert not any(command[1] == "push" for command in guard.commands)
