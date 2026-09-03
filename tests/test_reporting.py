"""ReportingAgent combines deterministic board facts into a report."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import groundtruth.__main__ as cli_module
from groundtruth.adapters.llm import LLMError, PromptName
from groundtruth.agents.reporting import ReportingAgent
from groundtruth.agents.steward import AuditResult
from groundtruth.config import RunMode, Settings
from groundtruth.contracts.discrepancy import (
    ActionVerb,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    ProposedAction,
)
from groundtruth.contracts.evidence import Evidence, EvidenceKind
from groundtruth.scoring import compute_score
from groundtruth.scoring.policy import load_policy
from tests.factories import AS_OF, board, frozen_clock, repo, ticket


class StubSteward:
    def __init__(self, result: AuditResult) -> None:
        self.result = result
        self.calls = 0

    def audit(self) -> AuditResult:
        self.calls += 1
        return self.result


class StubLLM:
    def __init__(self, response: str | Exception) -> None:
        self.response = response
        self.calls: list[tuple[PromptName, dict]] = []

    def complete(self, name: PromptName, variables: dict) -> str:
        self.calls.append((name, variables))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _discrepancy(type: DiscrepancyType, subject: str) -> Discrepancy:
    return Discrepancy.build(
        type=type,
        severity=DiscrepancySeverity.HIGH,
        subject=subject,
        evidence=[
            Evidence(
                kind=EvidenceKind.LEDGER,
                ref=subject,
                url=f"/{subject}",
                observed_at=AS_OF,
            )
        ],
        proposed_action=ProposedAction(verb=ActionVerb.NONE),
        detected_at=AS_OF,
        as_of=AS_OF,
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        run_mode=RunMode.REPLAY,
        workspace_dir=tmp_path / "workspace",
        artifacts_dir=tmp_path / "artifacts",
        fixtures_dir=tmp_path / "fixtures",
    )


def _audit_result() -> AuditResult:
    current_board = board(
        [
            ticket("AUTO-1", status="In Progress", points=3),
            ticket("AUTO-2", status="Done", points=5),
            ticket("AUTO-3", status="To Do", points=2, is_control=True),
        ]
    )
    current_repo = repo()
    policy = load_policy()
    return AuditResult(
        board=current_board,
        repo=current_repo,
        discrepancies=[
            _discrepancy(DiscrepancyType.UNVERIFIED_NO_MAPPING, "AUTO-1"),
            _discrepancy(DiscrepancyType.STALE_IN_PROGRESS, "AUTO-1"),
        ],
        policy=policy,
        clock=frozen_clock(),
    )


def test_report_writes_llm_prose_and_compatible_score_delta(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    audit = _audit_result()
    current_score = compute_score(audit.board, audit.repo, audit.clock, audit.policy)
    prior = {
        "score": {
            "total": current_score.total - 0.1,
            "policy_hash": current_score.policy_hash,
            "dimensions": [
                {"name": dim.name, "value": dim.value}
                for dim in current_score.dimensions
            ],
        }
    }
    prior_path = settings.artifacts_dir / "run_20260901-100000_score" / "score.json"
    prior_path.parent.mkdir(parents=True)
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    llm = StubLLM(
        "## Standup\nWork is moving.\n\n## Sprint health\nCapacity is tracked.\n\n## Score delta\nCompared with the prior run."
    )

    result = ReportingAgent(
        settings=settings,
        steward=StubSteward(audit),
        llm=llm,
    ).report(tmp_path / "run")

    assert result.health.velocity_forecast == 5
    assert result.health.capacity == 5
    assert result.health.open_discrepancies == 2
    assert result.health.unverified_count == 1
    assert result.health.stale_count == 1
    assert [item.jira_key for item in result.items] == ["AUTO-1"]
    assert result.items[0].discrepancy_count == 2
    assert result.delta is not None
    assert result.delta.previous_run_id == "run_20260901-100000_score"
    assert result.delta.overall_delta == 0.1
    assert result.prose_source == "llm"
    assert llm.calls[0][0] is PromptName.REPORT_PROSE
    assert (tmp_path / "run" / "report.json").exists()
    assert (tmp_path / "run" / "report.md").read_text(encoding="utf-8") == result.prose + "\n"


def test_report_uses_template_when_prose_is_unavailable(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    audit = _audit_result()

    result = ReportingAgent(
        settings=settings,
        steward=StubSteward(audit),
        llm=StubLLM(LLMError("fixture missing")),
    ).report(tmp_path / "run")

    assert result.delta is None
    assert result.prose_source == "template"
    assert "## Standup" in result.prose
    assert "## Sprint health" in result.prose
    assert "## Score delta\nNo comparable prior run." in result.prose


def test_report_cli_rejects_propose_mode() -> None:
    result = CliRunner().invoke(cli_module.cli, ["--mode", "propose", "report"])

    assert result.exit_code != 0
    assert "report is read-only" in result.output


def test_report_cli_uses_read_only_stack(tmp_path: Path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    captured: dict[str, object] = {}

    class StubReporter:
        def report(self, run_dir: Path):
            captured["run_dir"] = run_dir
            return type(
                "StubResult",
                (),
                {
                    "prose": "## Standup\nReady.\n\n## Sprint health\nHealthy.\n\n## Score delta\nNo comparable prior run."
                },
            )()

    def stack(received: Settings, mode: RunMode, ledger=None) -> StubReporter:
        captured["settings"] = received
        captured["mode"] = mode
        captured["ledger"] = ledger
        return StubReporter()

    monkeypatch.setattr(
        cli_module.Settings, "from_env", classmethod(lambda _cls: settings)
    )
    monkeypatch.setattr(cli_module, "_report_stack", stack)

    result = CliRunner().invoke(cli_module.cli, ["report"])

    assert result.exit_code == 0, result.output
    assert "## Standup" in result.output
    assert captured["mode"] is RunMode.REPLAY
    assert captured["run_dir"] == Path(captured["ledger"].ledger_path).parent
