"""Red gate classifier.

Determines whether the first pytest run after authoring tests is a valid
"red" state: every acceptance-criterion-bound test must fail with an
assertion failure, proving the tests are wired correctly and the codebase
is not already satisfying them.
"""

from __future__ import annotations

from groundtruth.contracts.delivery import RedGateClassification, RedGateReport
from groundtruth.contracts.testrun import TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import FailureKind


def _classify_failure(message: str) -> FailureKind:
    lowered = (message or "").lower()
    if "collection" in lowered or "collected" in lowered:
        return FailureKind.COLLECTION_ERROR
    if "importerror" in lowered or "modulenotfounderror" in lowered:
        return FailureKind.IMPORT_ERROR
    if "assertion" in lowered or "assert" in lowered:
        return FailureKind.ASSERTION
    # Default to assertion because a normal test failure is an assertion.
    return FailureKind.ASSERTION


def classify(run: TestRunResult, bound_node_ids: set[str]) -> RedGateReport:
    """Classify each bound node and decide whether the red gate is valid."""
    classifications: list[RedGateClassification] = []
    valid = True

    for node_id in sorted(bound_node_ids):
        collected = node_id in run.collected_node_ids
        outcome = run.tests.get(node_id)

        if not collected or outcome is None:
            classifications.append(
                RedGateClassification(
                    node_id=node_id,
                    failed=True,
                    failure_kind=FailureKind.COLLECTION_ERROR,
                    message_excerpt="node not collected",
                )
            )
            valid = False
            continue

        if outcome.status == TestOutcomeStatus.FAILED:
            kind = _classify_failure(outcome.message)
            classifications.append(
                RedGateClassification(
                    node_id=node_id,
                    failed=True,
                    failure_kind=kind,
                    message_excerpt=outcome.message[:200],
                )
            )
            if kind != FailureKind.ASSERTION:
                valid = False
        elif outcome.status == TestOutcomeStatus.ERROR:
            kind = _classify_failure(outcome.message)
            classifications.append(
                RedGateClassification(
                    node_id=node_id,
                    failed=True,
                    failure_kind=kind,
                    message_excerpt=outcome.message[:200],
                )
            )
            valid = False
        else:
            classifications.append(
                RedGateClassification(
                    node_id=node_id,
                    failed=False,
                    message_excerpt=outcome.message[:200],
                )
            )
            valid = False

    return RedGateReport(classifications=classifications, is_valid_red=valid)
