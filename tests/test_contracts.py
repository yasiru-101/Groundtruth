"""Tests for data contracts.

Core invariant: a Discrepancy cannot be constructed without evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from groundtruth.contracts import (
    AcceptanceCriterion,
    DedupeVerdict,
    DefinitionOfReadyResult,
    DimensionScore,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    Evidence,
    EvidenceKind,
    LedgerEntry,
    LedgerMode,
    LedgerOutcome,
    ProposedAction,
    ActionVerb,
    Story,
    StoryStatus,
    TestRunResult,
    TraceLink,
    TraceMatrixRow,
    TraceMatrixStatus,
    TruthfulnessScore,
)


def _make_evidence() -> Evidence:
    return Evidence(
        kind=EvidenceKind.COMMIT,
        ref="abc123def456",
        url="https://github.com/example/repo/commit/abc123def456",
        observed_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        detail={"message": "fix: resolve stale ticket"},
    )


def _make_action() -> ProposedAction:
    return ProposedAction(
        verb=ActionVerb.COMMENT,
        target="AUTO-14",
        params={"body": "This ticket appears stale."},
    )


class TestDiscrepancyEvidenceValidator:
    """The whole thesis: a discrepancy without evidence cannot be constructed."""

    def test_discrepancy_without_evidence_raises(self) -> None:
        with pytest.raises(ValidationError, match="evidence"):
            Discrepancy(
                discrepancy_id="test",
                type=DiscrepancyType.STALE_IN_PROGRESS,
                severity=DiscrepancySeverity.MEDIUM,
                subject="AUTO-14",
                evidence=[],
                proposed_action=_make_action(),
                detected_at=datetime.now(timezone.utc),
                as_of=datetime.now(timezone.utc),
            )

    def test_discrepancy_with_evidence_succeeds(self) -> None:
        d = Discrepancy(
            discrepancy_id="test",
            type=DiscrepancyType.STALE_IN_PROGRESS,
            severity=DiscrepancySeverity.MEDIUM,
            subject="AUTO-14",
            evidence=[_make_evidence()],
            proposed_action=_make_action(),
            detected_at=datetime.now(timezone.utc),
            as_of=datetime.now(timezone.utc),
        )
        assert len(d.evidence) == 1

    def test_discrepancy_build_classmethod(self) -> None:
        d = Discrepancy.build(
            type=DiscrepancyType.MERGED_PR_TICKET_OPEN,
            severity=DiscrepancySeverity.HIGH,
            subject="AUTO-15",
            evidence=[_make_evidence()],
            proposed_action=_make_action(),
            detected_at=datetime.now(timezone.utc),
            as_of=datetime.now(timezone.utc),
        )
        assert d.discrepancy_id
        assert d.type == DiscrepancyType.MERGED_PR_TICKET_OPEN

    def test_discrepancy_dedupes_by_id(self) -> None:
        ev = _make_evidence()
        d1 = Discrepancy.build(
            type=DiscrepancyType.STALE_IN_PROGRESS,
            severity=DiscrepancySeverity.MEDIUM,
            subject="AUTO-14",
            evidence=[ev],
            proposed_action=_make_action(),
            detected_at=datetime.now(timezone.utc),
            as_of=datetime.now(timezone.utc),
        )
        d2 = Discrepancy.build(
            type=DiscrepancyType.STALE_IN_PROGRESS,
            severity=DiscrepancySeverity.MEDIUM,
            subject="AUTO-14",
            evidence=[ev],
            proposed_action=_make_action(),
            detected_at=datetime.now(timezone.utc),
            as_of=datetime.now(timezone.utc),
        )
        assert d1.discrepancy_id == d2.discrepancy_id


class TestEvidenceContract:
    def test_evidence_requires_ref(self) -> None:
        with pytest.raises(ValidationError):
            Evidence(
                kind=EvidenceKind.COMMIT,
                ref="",
                url="https://example.com",
                observed_at=datetime.now(timezone.utc),
            )

    def test_evidence_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            Evidence(
                kind=EvidenceKind.COMMIT,
                ref="abc",
                url="https://example.com",
                observed_at=datetime.now(timezone.utc),
                unexpected_field="oops",
            )


class TestStoryContract:
    def test_story_creation(self) -> None:
        s = Story(
            idempotency_key="test-key",
            summary="Implement login page",
            acceptance_criteria=[
                AcceptanceCriterion(
                    ac_id="AUTO-14-AC1",
                    given="a user is on the login page",
                    when="they enter valid credentials",
                    then="they are redirected to the dashboard",
                    raw="Given a user is on the login page When they enter valid credentials Then they are redirected to the dashboard",
                    is_wellformed=True,
                )
            ],
            points=5,
            components=["auth"],
        )
        assert s.status == StoryStatus.DRAFT
        assert len(s.acceptance_criteria) == 1

    def test_dor_result(self) -> None:
        dor = DefinitionOfReadyResult(
            passed=False,
            failures=["NO_AC", "NO_POINTS"],
            checked_at=datetime.now(timezone.utc),
        )
        assert not dor.passed
        assert "NO_AC" in dor.failures


class TestDedupeVerdict:
    def test_dedupe_not_auto_resolved(self) -> None:
        d = DedupeVerdict(
            candidate_jira_keys=["AUTO-10"],
            similarity=0.85,
            method="token_set",
            threshold=0.8,
            human_confirmed=None,
        )
        assert d.human_confirmed is None


class TestProposedAction:
    def test_requires_approval_defaults_true(self) -> None:
        a = ProposedAction(verb=ActionVerb.TRANSITION, target="AUTO-14")
        assert a.requires_approval is True

    def test_requires_approval_cannot_default_false(self) -> None:
        a = ProposedAction(verb=ActionVerb.NONE, target="", requires_approval=True)
        assert a.requires_approval is True


class TestTraceContracts:
    def test_trace_link(self) -> None:
        tl = TraceLink(
            ac_id="AUTO-14-AC1",
            test_node_id="tests/test_login.py::test_valid_login",
            bound_at=datetime.now(timezone.utc),
            test_file_hash="sha256:abc123",
        )
        assert tl.bound_by == "manifest"

    def test_trace_matrix_row_missing_status(self) -> None:
        row = TraceMatrixRow(
            ac_id="AUTO-14-AC1",
            ac_text="Given X When Y Then Z",
            status=TraceMatrixStatus.MISSING,
        )
        assert row.status == TraceMatrixStatus.MISSING
        assert row.test_node_ids == []


class TestScoreContracts:
    def test_dimension_score_null(self) -> None:
        ds = DimensionScore(
            name="done_integrity",
            value=None,
            excluded_reason="No Done tickets in board",
        )
        assert ds.value is None

    def test_truthfulness_score(self) -> None:
        ts = TruthfulnessScore(
            total=42.5,
            dimensions=[
                DimensionScore(name="ac_validity", value=0.8, numerator=8, denominator=10, weight=0.2),
            ],
            policy_version="1.0.0",
            policy_hash="sha256:abc",
            as_of=datetime.now(timezone.utc),
            board_snapshot_hash="sha256:def",
        )
        assert ts.total == 42.5


class TestApprovalContract:
    def test_changeset_hash_stable(self) -> None:
        from groundtruth.safety.approval import ChangeItem, ChangeSet

        cs = ChangeSet(
            items=[ChangeItem(action="create", subject="AUTO-14", params={"summary": "test"})],
            created_at=datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        )
        h1 = cs.compute_hash()
        h2 = cs.compute_hash()
        assert h1 == h2
        assert len(h1) == 64
