"""Tests for the delivery red gate classifier."""

from __future__ import annotations

from groundtruth.contracts.delivery import RedGateReport
from groundtruth.contracts.testrun import TestOutcome, TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import FailureKind
from groundtruth.delivery.red_gate import classify


def _run(outcomes: dict[str, tuple[TestOutcomeStatus, str]]) -> TestRunResult:
    return TestRunResult(
        run_id="run-1",
        exit_code=1,
        collected_node_ids=set(outcomes),
        tests={
            node: TestOutcome(node_id=node, status=status, message=message)
            for node, (status, message) in outcomes.items()
        },
    )


class TestRedGate:
    def test_valid_red_when_all_assertion_failures(self) -> None:
        run = _run(
            {
                "tests/test_a.py::test_one": (
                    TestOutcomeStatus.FAILED,
                    "AssertionError: expected 1 got 2",
                ),
            }
        )
        report = classify(run, {"tests/test_a.py::test_one"})
        assert report.is_valid_red
        assert report.classifications[0].failure_kind == FailureKind.ASSERTION

    def test_invalid_when_bound_node_passes(self) -> None:
        run = _run(
            {
                "tests/test_a.py::test_one": (TestOutcomeStatus.PASSED, ""),
            }
        )
        report = classify(run, {"tests/test_a.py::test_one"})
        assert not report.is_valid_red
        assert not report.classifications[0].failed

    def test_invalid_when_import_error(self) -> None:
        run = _run(
            {
                "tests/test_a.py::test_one": (
                    TestOutcomeStatus.FAILED,
                    "ImportError: no module named 'foo'",
                ),
            }
        )
        report = classify(run, {"tests/test_a.py::test_one"})
        assert not report.is_valid_red
        assert report.classifications[0].failure_kind == FailureKind.IMPORT_ERROR

    def test_invalid_when_not_collected(self) -> None:
        run = _run({})
        report = classify(run, {"tests/test_a.py::test_one"})
        assert not report.is_valid_red
        assert report.classifications[0].failure_kind == FailureKind.COLLECTION_ERROR

    def test_error_status_collection_error(self) -> None:
        run = _run(
            {
                "tests/test_a.py::test_one": (
                    TestOutcomeStatus.ERROR,
                    "collection error during setup",
                ),
            }
        )
        report = classify(run, {"tests/test_a.py::test_one"})
        assert not report.is_valid_red
        assert report.classifications[0].failure_kind == FailureKind.COLLECTION_ERROR
