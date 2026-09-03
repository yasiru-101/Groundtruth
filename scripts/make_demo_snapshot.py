"""Regenerate the self-contained demo snapshot used by the dashboard.

The script:
1. Copies the root fixtures into demo/fixtures.
2. Runs audit, score, report, and plan in replay mode into demo/artifacts.
3. Renames timestamped run directories to stable names (run_demo_*).
4. Synthesizes a delivery run for AUTO-2 with a green PR and trace manifest.
5. Verifies every ledger chain in demo/artifacts.

Run from the repository root:
    python scripts/make_demo_snapshot.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT_ROOT / "demo"
FIXTURES_DIR = DEMO_DIR / "fixtures"
ARTIFACTS_DIR = DEMO_DIR / "artifacts"
ROOT_FIXTURES_DIR = PROJECT_ROOT / "fixtures"

DEMO_ENV = {
    **os.environ,
    "GT_FIXTURES_DIR": str(FIXTURES_DIR),
    "GT_ARTIFACTS_DIR": str(ARTIFACTS_DIR),
}


def run_groundtruth(command: str, *args: str) -> Path:
    """Run a groundtruth CLI command in replay mode and return the run directory."""
    cmd = [sys.executable, "-m", "groundtruth", "--run-mode", "replay", command, *args]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, env=DEMO_ENV, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    # Find the run directory emitted on the last line.
    last_line = result.stdout.strip().splitlines()[-1]
    marker = ": "
    if marker in last_line:
        run_dir = Path(last_line.split(marker, 1)[1].strip())
        if run_dir.exists():
            return run_dir
    raise RuntimeError(f"Could not detect run directory in output: {last_line!r}")


def reset_demo_dirs() -> None:
    """Remove old demo fixtures/artifacts and recreate them."""
    if FIXTURES_DIR.exists():
        shutil.rmtree(FIXTURES_DIR)
    if ARTIFACTS_DIR.exists():
        shutil.rmtree(ARTIFACTS_DIR)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def copy_fixtures() -> None:
    """Copy root fixtures into demo/fixtures for offline replay."""
    for fixture in sorted(ROOT_FIXTURES_DIR.glob("*.json")):
        shutil.copy2(fixture, FIXTURES_DIR / fixture.name)


def rename_run(run_dir: Path, label: str) -> Path:
    """Rename a timestamped run directory to a stable demo name."""
    stable = ARTIFACTS_DIR / f"run_demo_{label}"
    if stable.exists():
        shutil.rmtree(stable)
    run_dir.rename(stable)
    return stable


def _synthesize_delivery_run() -> Path:
    """Create a realistic but synthetic delivery snapshot for AUTO-2."""
    from groundtruth.contracts.delivery import (
        AuthoredTests,
        DeliveryPhase,
        DeliveryResult,
        RedGateClassification,
        RedGateReport,
        RepairIteration,
    )
    from groundtruth.contracts.ledger import LedgerMode
    from groundtruth.contracts.testrun import TestOutcome, TestOutcomeStatus, TestRunResult
    from groundtruth.contracts.trace import FailureKind, TraceLink
    from groundtruth.ledger.writer import LedgerWriter
    from groundtruth.trace.manifest import TraceManifest
    from groundtruth.trace.reconcile import build_manifest

    run_dir = ARTIFACTS_DIR / "run_demo_deliver"
    run_dir.mkdir(parents=True, exist_ok=True)
    ledger = LedgerWriter(run_dir / "ledger.jsonl")

    now = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    ticket_key = "AUTO-2"
    branch = "feature/AUTO-2"
    pr_url = "https://github.com/yasiru-101/Groundtruth/pull/2"
    head_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    test_file = "tests/test_auto_2.py"

    # Red gate: one failing assertion proves the test is real.
    red_gate = RedGateReport(
        is_valid_red=True,
        classifications=[
            RedGateClassification(
                node_id="tests/test_auto_2.py::test_profile_update",
                failed=True,
                failure_kind=FailureKind.ASSERTION,
                message_excerpt="assert profile.name == 'Ada'",
            )
        ],
    )

    # One repair iteration turns the red gate green.
    iterations = [
        RepairIteration(
            iteration=1,
            phase="implement",
            files_changed=["src/profile.py", test_file],
            red_gate_valid=True,
            green=True,
            notes=["Implemented profile name update path."],
        )
    ]

    result = DeliveryResult(
        ticket_key=ticket_key,
        branch=branch,
        phase=DeliveryPhase.PR,
        red_gate=red_gate,
        iterations=iterations,
        green=True,
        pr_url=pr_url,
        draft=False,
        head_sha=head_sha,
        run_dir=str(run_dir),
        notes=["Delivered through red/green gate with traceable tests."],
    )

    (run_dir / "delivery_result.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )

    # Trace manifest binding the acceptance criteria to the test node.
    bindings = [
        TraceLink(
            ac_id="AUTO-2#1",
            test_node_id="tests/test_auto_2.py::test_profile_update",
            bound_by="delivery",
            bound_at=now,
            test_file_hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        )
    ]
    test_run = TestRunResult(
        run_id=ledger.run_id,
        exit_code=0,
        collected_node_ids={"tests/test_auto_2.py::test_profile_update"},
        tests={
            "tests/test_auto_2.py::test_profile_update": TestOutcome(
                node_id="tests/test_auto_2.py::test_profile_update",
                status=TestOutcomeStatus.PASSED,
            )
        },
    )
    manifest = build_manifest(ledger.run_id, now, bindings, test_run)
    (run_dir / "trace_manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )

    # Authored tests artifact for the timeline.
    authored = AuthoredTests(
        test_file=test_file,
        bindings=bindings,
        content='def test_profile_update():\n    profile = update_profile(name="Ada")\n    assert profile.name == "Ada"\n',
    )
    (run_dir / "authored_tests.json").write_text(
        json.dumps(authored.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )

    ledger.append(
        actor="delivery",
        action="delivery.run",
        mode=LedgerMode.REPLAY,
        subject=ticket_key,
        inputs_hash=ledger.run_id,
        outputs_hash=head_sha,
        evidence=[
            {"phase": "red_gate", "valid": True},
            {"phase": "green_gate", "green": True},
            {"phase": "pr", "url": pr_url},
            {"trace_bindings": len(bindings)},
        ],
    )
    ledger.append(
        actor="delivery",
        action="delivery.trace",
        mode=LedgerMode.REPLAY,
        subject=ticket_key,
        evidence=[{"manifest": "trace_manifest.json"}],
    )

    return run_dir


def verify_ledgers() -> None:
    """Verify every ledger chain in demo/artifacts."""
    from groundtruth.ledger.reader import verify_chain

    failures = []
    for ledger_path in sorted(ARTIFACTS_DIR.glob("run_*/ledger.jsonl")):
        try:
            verify_chain(ledger_path)
        except Exception as exc:
            failures.append(f"{ledger_path.relative_to(PROJECT_ROOT)}: {exc}")
    if failures:
        raise RuntimeError("Ledger verification failed:\n" + "\n".join(failures))


def main() -> int:
    reset_demo_dirs()
    copy_fixtures()

    audit_dir = run_groundtruth("audit")
    score_dir = run_groundtruth("score")
    report_dir = run_groundtruth("report")
    plan_dir = run_groundtruth("plan")

    rename_run(audit_dir, "audit")
    rename_run(score_dir, "score")
    rename_run(report_dir, "report")
    rename_run(plan_dir, "plan")

    _synthesize_delivery_run()

    verify_ledgers()

    print("Demo snapshot ready in demo/artifacts")
    for run_dir in sorted(ARTIFACTS_DIR.glob("run_demo_*")):
        print(f"  {run_dir.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
