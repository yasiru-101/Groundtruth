"""Tests for trace reconciliation and manifest building."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from groundtruth.contracts.testrun import TestOutcome, TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import TraceLink, TraceMatrixStatus
from groundtruth.trace.manifest import TraceManifest
from groundtruth.trace.reconcile import (
    build_manifest,
    canonical_bytes,
    manifest_hash,
    merge_bindings,
    reconcile,
)


def _link(ac_id: str, node_id: str, h: str = "sha256:abc") -> TraceLink:
    return TraceLink(
        ac_id=ac_id,
        test_node_id=node_id,
        bound_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        test_file_hash=h,
    )


def _run(
    collected: list[str],
    outcomes: dict[str, TestOutcomeStatus],
    exit_code: int = 0,
) -> TestRunResult:
    return TestRunResult(
        run_id="run-1",
        exit_code=exit_code,
        collected_node_ids=set(collected),
        tests={
            node: TestOutcome(node_id=node, status=status)
            for node, status in outcomes.items()
        },
    )


class TestReconcile:
    def test_all_bound_passed(self) -> None:
        bindings = [
            _link("AUTO-1#1", "tests/test_a.py::test_one"),
        ]
        run = _run(
            collected=["tests/test_a.py::test_one"],
            outcomes={"tests/test_a.py::test_one": TestOutcomeStatus.PASSED},
        )
        report = reconcile(bindings, run)
        assert report.bound_node_ids == {"tests/test_a.py::test_one"}
        assert report.missing_node_ids == set()
        assert report.unbound_failures == []
        assert report.ac_status == {"AUTO-1#1": TraceMatrixStatus.PASSED}

    def test_bound_node_missing_from_collection(self) -> None:
        bindings = [_link("AUTO-1#1", "tests/test_a.py::test_one")]
        run = _run(collected=[], outcomes={})
        report = reconcile(bindings, run)
        assert report.missing_node_ids == {"tests/test_a.py::test_one"}
        assert report.ac_status == {"AUTO-1#1": TraceMatrixStatus.NOT_COLLECTED}

    def test_bound_node_failed(self) -> None:
        bindings = [_link("AUTO-1#1", "tests/test_a.py::test_one")]
        run = _run(
            collected=["tests/test_a.py::test_one"],
            outcomes={"tests/test_a.py::test_one": TestOutcomeStatus.FAILED},
        )
        report = reconcile(bindings, run)
        assert report.ac_status == {"AUTO-1#1": TraceMatrixStatus.FAILED}

    def test_unbound_failure_reported(self) -> None:
        bindings = [_link("AUTO-1#1", "tests/test_a.py::test_one")]
        run = _run(
            collected=[
                "tests/test_a.py::test_one",
                "tests/test_a.py::test_two",
            ],
            outcomes={
                "tests/test_a.py::test_one": TestOutcomeStatus.PASSED,
                "tests/test_a.py::test_two": TestOutcomeStatus.FAILED,
            },
        )
        report = reconcile(bindings, run)
        assert report.unbound_failures == ["tests/test_a.py::test_two"]

    def test_worst_status_wins(self) -> None:
        bindings = [
            _link("AUTO-1#1", "tests/test_a.py::test_one"),
            _link("AUTO-1#1", "tests/test_a.py::test_two"),
        ]
        run = _run(
            collected=[
                "tests/test_a.py::test_one",
                "tests/test_a.py::test_two",
            ],
            outcomes={
                "tests/test_a.py::test_one": TestOutcomeStatus.PASSED,
                "tests/test_a.py::test_two": TestOutcomeStatus.FAILED,
            },
        )
        report = reconcile(bindings, run)
        assert report.ac_status == {"AUTO-1#1": TraceMatrixStatus.FAILED}


class TestBuildManifest:
    def test_manifest_has_snapshot(self) -> None:
        bindings = [_link("AUTO-1#1", "tests/test_a.py::test_one")]
        run = _run(
            collected=["tests/test_a.py::test_one"],
            outcomes={"tests/test_a.py::test_one": TestOutcomeStatus.PASSED},
        )
        created = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        manifest = build_manifest("run-1", created, bindings, run)
        assert manifest.trace_version == "1.0"
        assert manifest.run_id == "run-1"
        assert manifest.test_snapshot.outcomes == {
            "tests/test_a.py::test_one": "passed"
        }
        assert manifest.test_snapshot.collected_node_ids == [
            "tests/test_a.py::test_one"
        ]


class TestMergeBindings:
    def test_replaces_only_current_ticket(self) -> None:
        prior = [
            _link("AUTO-1#1", "tests/test_a.py::old"),
            _link("AUTO-2#1", "tests/test_b.py::keep"),
        ]
        new = [_link("AUTO-1#1", "tests/test_a.py::new")]
        merged = merge_bindings(prior, new, "AUTO-1")
        assert [link.ac_id for link in merged] == ["AUTO-2#1", "AUTO-1#1"]
        assert merged[1].test_node_id == "tests/test_a.py::new"

    def test_no_prior_returns_new(self) -> None:
        new = [_link("AUTO-1#1", "tests/test_a.py::new")]
        assert merge_bindings([], new, "AUTO-1") == new


class TestCanonicalBytes:
    def test_deterministic_and_stable_hash(self) -> None:
        bindings = [_link("AUTO-1#1", "tests/test_a.py::test_one")]
        run = _run(
            collected=["tests/test_a.py::test_one"],
            outcomes={"tests/test_a.py::test_one": TestOutcomeStatus.PASSED},
        )
        manifest = build_manifest(
            "run-1", datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc), bindings, run
        )
        b1 = canonical_bytes(manifest)
        b2 = canonical_bytes(manifest)
        assert b1 == b2
        assert manifest_hash(manifest) == manifest_hash(manifest)
        assert len(manifest_hash(manifest)) == 64

    def test_loads_back_to_equivalent_manifest(self) -> None:
        import json

        bindings = [_link("AUTO-1#1", "tests/test_a.py::test_one")]
        run = _run(
            collected=["tests/test_a.py::test_one"],
            outcomes={"tests/test_a.py::test_one": TestOutcomeStatus.PASSED},
        )
        manifest = build_manifest(
            "run-1", datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc), bindings, run
        )
        loaded = TraceManifest.model_validate(json.loads(canonical_bytes(manifest)))
        assert loaded.run_id == manifest.run_id
        assert loaded.bindings[0].ac_id == manifest.bindings[0].ac_id
