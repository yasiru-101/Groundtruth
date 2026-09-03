"""Tests for the delivery PR body renderer."""

from __future__ import annotations

from groundtruth.contracts.delivery import DeliveryPhase, DeliveryResult, RedGateReport
from groundtruth.contracts.trace import TraceMatrixRow, TraceMatrixStatus
from groundtruth.delivery.pr_body import render


def _result(**kwargs: object) -> DeliveryResult:
    defaults = {
        "ticket_key": "AUTO-1",
        "branch": "deliver/AUTO-1",
        "phase": DeliveryPhase.PR,
        "red_gate": RedGateReport(classifications=[], is_valid_red=True),
        "green": True,
        "run_dir": "/tmp/run",
    }
    defaults.update(kwargs)
    return DeliveryResult(**defaults)


class TestPRBody:
    def test_includes_traceability_matrix(self) -> None:
        result = _result()
        rows = [
            TraceMatrixRow(
                ac_id="AUTO-1#1",
                ac_text="Given X When Y Then Z",
                test_node_ids=["tests/test_a.py::test_one"],
                status=TraceMatrixStatus.PASSED,
            )
        ]
        body = render(result, rows)
        assert "## Traceability matrix" in body
        assert "AUTO-1#1" in body
        assert "tests/test_a.py::test_one" in body
        assert "passed" in body

    def test_draft_banner_when_not_green(self) -> None:
        result = _result(green=False, draft=True)
        body = render(result, [])
        assert "DRAFT PR" in body
        assert "implementation did not reach a green gate" in body

    def test_green_no_draft_banner(self) -> None:
        result = _result(green=True)
        body = render(result, [])
        assert "DRAFT PR" not in body

    def test_repair_log_present(self) -> None:
        from groundtruth.contracts.delivery import RepairIteration

        result = _result(
            iterations=[
                RepairIteration(
                    iteration=1,
                    phase="implement",
                    files_changed=["src/app.py"],
                    green=True,
                )
            ]
        )
        body = render(result, [])
        assert "## Repair log" in body
        assert "src/app.py" in body
