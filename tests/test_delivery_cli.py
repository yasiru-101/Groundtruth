"""CLI safety tests for the approval-gated delivery command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import groundtruth.__main__ as cli_module
from groundtruth.config import Settings
from groundtruth.contracts.delivery import DeliveryPhase, DeliveryResult, RedGateReport
from groundtruth.contracts.ledger import LedgerMode
from groundtruth.safety.approval import ChangeItem, propose_changeset


def _live_settings(tmp_path: Path) -> Settings:
    return Settings(
        jira_base_url="https://jira.example.test",
        jira_email="operator@example.test",
        jira_api_token="jira-token",
        github_token="github-token",
        github_repo_owner="owner",
        github_repo_name="repo",
        llm_api_key="llm-token",
        llm_model="model",
        llm_base_url="https://llm.example.test",
        workspace_dir=tmp_path / "workspace",
        artifacts_dir=tmp_path / "artifacts",
        fixtures_dir=tmp_path / "fixtures",
    )


def test_deliver_dry_run_creates_no_artifacts(tmp_path: Path, monkeypatch) -> None:
    settings = _live_settings(tmp_path)
    monkeypatch.setattr(
        cli_module.Settings, "from_env", classmethod(lambda _cls: settings)
    )

    result = CliRunner().invoke(cli_module.cli, ["deliver", "AUTO-1"])

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert "Would deliver ticket: AUTO-1" in result.output
    assert not settings.artifacts_dir.exists()


def test_deliver_propose_writes_single_ticket_changeset_and_ledger(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _live_settings(tmp_path)
    monkeypatch.setattr(
        cli_module.Settings, "from_env", classmethod(lambda _cls: settings)
    )

    result = CliRunner().invoke(
        cli_module.cli, ["--mode", "propose", "deliver", "AUTO-1"]
    )

    assert result.exit_code == 0, result.output
    changesets = list((settings.artifacts_dir / "changesets").glob("*.json"))
    assert len(changesets) == 1
    changeset = json.loads(changesets[0].read_text(encoding="utf-8"))
    assert changeset["items"] == [
        {"action": "delivery.deliver", "subject": "AUTO-1", "params": {}}
    ]
    ledger_path = next(settings.artifacts_dir.glob("run_*_deliver/ledger.jsonl"))
    entry = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert entry["action"] == "delivery.propose"
    assert entry["mode"] == LedgerMode.PROPOSE.value


def test_deliver_apply_requires_live_mode(tmp_path: Path, monkeypatch) -> None:
    settings = _live_settings(tmp_path)
    changeset = propose_changeset(
        settings.artifacts_dir,
        [ChangeItem(action="delivery.deliver", subject="AUTO-1")],
    )
    monkeypatch.setattr(
        cli_module.Settings, "from_env", classmethod(lambda _cls: settings)
    )

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "--mode",
            "apply",
            "--run-mode",
            "replay",
            "--changeset",
            changeset.compute_hash(),
            "deliver",
            "AUTO-1",
        ],
    )

    assert result.exit_code != 0
    assert "deliver requires --run-mode live" in result.output


def test_deliver_apply_uses_approved_ticket_and_records_approval(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _live_settings(tmp_path)
    changeset = propose_changeset(
        settings.artifacts_dir,
        [ChangeItem(action="delivery.deliver", subject="AUTO-1")],
    )
    captured: dict[str, object] = {}

    class FakeDeliveryAgent:
        def deliver(self, key: str, run_dir: Path | None = None) -> DeliveryResult:
            captured["key"] = key
            captured["run_dir"] = run_dir
            return DeliveryResult(
                ticket_key=key,
                branch="deliver/auto-1",
                phase=DeliveryPhase.PR,
                red_gate=RedGateReport(),
                green=True,
                pr_url="https://github.com/owner/repo/pull/1",
                run_dir=str(run_dir),
            )

    def fake_stack(
        received_settings: Settings,
        run_mode: object,
        ledger: object = None,
        approval: object = None,
    ) -> FakeDeliveryAgent:
        captured["settings"] = received_settings
        captured["run_mode"] = run_mode
        captured["ledger"] = ledger
        captured["approval"] = approval
        return FakeDeliveryAgent()

    monkeypatch.setattr(
        cli_module.Settings, "from_env", classmethod(lambda _cls: settings)
    )
    monkeypatch.setattr(cli_module, "_delivery_stack", fake_stack)

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "--mode",
            "apply",
            "--run-mode",
            "live",
            "--changeset",
            changeset.compute_hash(),
            "deliver",
            "AUTO-1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Delivery AUTO-1: green PR https://github.com/owner/repo/pull/1" in result.output
    assert captured["key"] == "AUTO-1"
    assert captured["run_mode"].value == "live"
    assert captured["approval"].changeset_hash == changeset.compute_hash()
    assert captured["run_dir"] == Path(captured["ledger"].ledger_path).parent


def test_deliver_apply_rejects_a_changeset_for_another_ticket(
    tmp_path: Path, monkeypatch
) -> None:
    settings = _live_settings(tmp_path)
    changeset = propose_changeset(
        settings.artifacts_dir,
        [ChangeItem(action="delivery.deliver", subject="AUTO-2")],
    )
    monkeypatch.setattr(
        cli_module.Settings, "from_env", classmethod(lambda _cls: settings)
    )

    result = CliRunner().invoke(
        cli_module.cli,
        [
            "--mode",
            "apply",
            "--run-mode",
            "live",
            "--changeset",
            changeset.compute_hash(),
            "deliver",
            "AUTO-1",
        ],
    )

    assert result.exit_code != 0
    assert "Changeset does not approve delivery of AUTO-1" in result.output
