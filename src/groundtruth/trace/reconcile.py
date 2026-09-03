"""Trace reconciler: bind authored tests to acceptance criteria and
build the traceability manifest from a pytest run.

Pure functions only: no adapter calls, no LLM, no git.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from groundtruth.contracts.testrun import TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import TraceLink, TraceMatrixRow, TraceMatrixStatus
from groundtruth.trace.manifest import TestSnapshotDoc, TraceManifest


@dataclass
class ReconcileReport:
    bound_node_ids: set[str]
    missing_node_ids: set[str]
    unbound_failures: list[str]
    ac_status: dict[str, TraceMatrixStatus]
    rows: list[TraceMatrixRow]


def _status_from_outcome(
    outcome: TestOutcomeStatus | None,
    collected: bool,
) -> TraceMatrixStatus:
    if not collected:
        return TraceMatrixStatus.NOT_COLLECTED
    if outcome is None:
        return TraceMatrixStatus.ERROR
    mapping = {
        TestOutcomeStatus.PASSED: TraceMatrixStatus.PASSED,
        TestOutcomeStatus.FAILED: TraceMatrixStatus.FAILED,
        TestOutcomeStatus.SKIPPED: TraceMatrixStatus.SKIPPED,
        TestOutcomeStatus.ERROR: TraceMatrixStatus.ERROR,
        TestOutcomeStatus.NOT_COLLECTED: TraceMatrixStatus.NOT_COLLECTED,
    }
    return mapping.get(outcome, TraceMatrixStatus.ERROR)


def reconcile(
    bindings: list[TraceLink],
    run: TestRunResult,
) -> ReconcileReport:
    """Compare claimed bindings against the actual pytest run.

    Per-AC status is the worst outcome among its bound nodes:
    NOT_COLLECTED > ERROR > FAILED > SKIPPED > PASSED > MISSING.
    """
    collected = set(run.collected_node_ids)
    outcomes = run.tests

    bound_node_ids: set[str] = set()
    ac_to_nodes: dict[str, list[str]] = {}
    for link in bindings:
        bound_node_ids.add(link.test_node_id)
        ac_to_nodes.setdefault(link.ac_id, []).append(link.test_node_id)

    missing_node_ids = bound_node_ids - collected

    failing = {
        node_id
        for node_id, outcome in outcomes.items()
        if outcome.status in {TestOutcomeStatus.FAILED, TestOutcomeStatus.ERROR}
    }
    unbound_failures = sorted(failing - bound_node_ids)

    ac_status: dict[str, TraceMatrixStatus] = {}
    rows: list[TraceMatrixRow] = []

    # Deterministic iteration order.
    for ac_id in sorted(ac_to_nodes):
        nodes = sorted(ac_to_nodes[ac_id])
        statuses: list[TraceMatrixStatus] = []
        for node_id in nodes:
            in_collected = node_id in collected
            outcome = outcomes.get(node_id)
            statuses.append(_status_from_outcome(outcome.status if outcome else None, in_collected))

        if not statuses:
            status = TraceMatrixStatus.MISSING
        else:
            # Worse ordinal wins.
            order = [
                TraceMatrixStatus.MISSING,
                TraceMatrixStatus.PASSED,
                TraceMatrixStatus.SKIPPED,
                TraceMatrixStatus.FAILED,
                TraceMatrixStatus.ERROR,
                TraceMatrixStatus.NOT_COLLECTED,
            ]
            status = max(statuses, key=lambda s: order.index(s))
        ac_status[ac_id] = status
        rows.append(
            TraceMatrixRow(
                ac_id=ac_id,
                ac_text="",
                test_node_ids=nodes,
                status=status,
            )
        )

    return ReconcileReport(
        bound_node_ids=bound_node_ids,
        missing_node_ids=missing_node_ids,
        unbound_failures=unbound_failures,
        ac_status=ac_status,
        rows=rows,
    )


def build_manifest(
    run_id: str,
    created_at: datetime,
    bindings: list[TraceLink],
    run: TestRunResult,
) -> TraceManifest:
    """Build a deterministic trace manifest from a reconciled run."""
    snapshot_outcomes: dict[str, str] = {}
    for node_id in sorted(run.collected_node_ids):
        outcome = run.tests.get(node_id)
        snapshot_outcomes[node_id] = (
            outcome.status.value if outcome else TestOutcomeStatus.NOT_COLLECTED.value
        )

    return TraceManifest(
        trace_version="1.0",
        run_id=run_id,
        created_at=created_at,
        bindings=list(bindings),
        test_snapshot=TestSnapshotDoc(
            ran_at=created_at,
            collected_node_ids=sorted(run.collected_node_ids),
            outcomes=snapshot_outcomes,
        ),
    )


def merge_bindings(
    prior: list[TraceLink],
    new: list[TraceLink],
    ticket_key: str,
) -> list[TraceLink]:
    """Replace bindings for ``ticket_key`` while preserving bindings for all
    other tickets. Required because ``latest_trace_manifest`` only reads the
    most recent run; without merging, a second delivery would erase earlier
    trace links.
    """
    prefix = f"{ticket_key}#"
    kept = [link for link in prior if not link.ac_id.startswith(prefix)]
    # Rebuild to avoid aliasing the input lists.
    return kept + list(new)


def canonical_bytes(manifest: TraceManifest) -> bytes:
    """Deterministic JSON serialization for workspace + artifact copies."""
    doc: dict[str, Any] = manifest.model_dump(mode="json")

    def _normalize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _normalize(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_normalize(v) for v in obj]
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    normalized = _normalize(doc)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def manifest_hash(manifest: TraceManifest) -> str:
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()
