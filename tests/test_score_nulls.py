"""Null dimensions: excluded from the denominator, exclusion printed.

An unmeasurable dimension must never be silently scored 1.0 — the most
common way a metric like this lies. Every null dimension shows up in the
rendered score and in the itemised evidence log, with its reason.
"""

from __future__ import annotations

import pytest

from factories import (
    ac,
    board,
    branch,
    check_run,
    days_ago,
    frozen_clock,
    merged_pr,
    repo,
    ticket,
)

from groundtruth.contracts.score import DimensionScore
from groundtruth.scoring.evidence_log import write_evidence_log
from groundtruth.scoring.policy import load_policy
from groundtruth.scoring.score import (
    DIMENSION_ORDER,
    compute_score,
    render_score,
    total_score,
)


def _dim(score, name: str):
    return next(d for d in score.dimensions if d.name == name)


def _done_ticket_with_proof() -> tuple:
    done = ticket(
        "AUTO-1",
        status="Done",
        branch="feature/AUTO-1",
        status_changed_at=days_ago(1),
        acceptance_criteria=[ac("AUTO-1#1")],
    )
    pr = merged_pr(3, "feature/AUTO-1")
    r = repo(
        [branch("feature/AUTO-1", [commit_tip()])],
        [pr],
        [check_run(pr.merge_sha)],
    )
    return done, r


def commit_tip():
    from factories import commit

    return commit("a" * 40, 2)


class TestEmptyBoard:
    def test_every_dimension_is_null_with_a_reason(self) -> None:
        score = compute_score(board(), repo(), frozen_clock())
        assert score.dimensions, "the score must still list all five dimensions"
        for dim in score.dimensions:
            assert dim.value is None
            assert dim.excluded_reason
        assert score.total == 0.0
        assert score.control_group is None

    def test_render_prints_each_exclusion(self) -> None:
        rendered = render_score(compute_score(board(), repo(), frozen_clock()))
        for name in DIMENSION_ORDER:
            assert f"{name:<20} EXCLUDED (" in rendered
        assert "EXCLUDED (no tickets on the board)" in rendered


class TestPartialNulls:
    def test_only_done_board_excludes_progress_and_staleness(self) -> None:
        done, r = _done_ticket_with_proof()
        score = compute_score(board([done]), r, frozen_clock())

        progress = _dim(score, "progress_integrity")
        assert progress.value is None
        assert progress.excluded_reason == "no In Progress tickets"
        staleness = _dim(score, "staleness_health")
        assert staleness.value is None
        assert staleness.excluded_reason == "no active tickets"
        assert _dim(score, "done_integrity").value == 1.0

        rendered = render_score(score)
        assert "EXCLUDED (no In Progress tickets)" in rendered
        assert "EXCLUDED (no active tickets)" in rendered

    def test_only_done_board_renormalizes_over_measured_weight(self) -> None:
        # Measured: ac + done, both 1.0, weight 0.50 (progress, staleness
        # AND duplication are all excluded — Done is not an active status).
        done, r = _done_ticket_with_proof()
        score = compute_score(board([done]), r, frozen_clock())
        assert score.total == pytest.approx(1.0)

    def test_only_in_progress_board_excludes_done(self) -> None:
        t = ticket(
            "AUTO-1",
            status="In Progress",
            branch="feature/AUTO-1",
            status_changed_at=days_ago(1),
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        from factories import commit

        r = repo([branch("feature/AUTO-1", [commit("a" * 40, 1)])])
        score = compute_score(board([t]), r, frozen_clock())

        done = _dim(score, "done_integrity")
        assert done.value is None
        assert done.excluded_reason == "no Done tickets"
        assert "EXCLUDED (no Done tickets)" in render_score(score)
        assert _dim(score, "progress_integrity").value == 1.0


class TestNeverSilentlyOne:
    def test_null_dimensions_do_not_contribute_one(self) -> None:
        # Done ticket with no merged PR: measured dims are ac 1/1 (0.15) and
        # done 0/1 (0.35). Progress, staleness AND duplication are excluded
        # (Done is terminal, so no active tickets) — they must not sneak in
        # as 1.0: that would give 0.65 instead of 0.15/0.50 = 0.30.
        done = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        r = repo([branch("feature/AUTO-1", [])])
        score = compute_score(board([done]), r, frozen_clock())

        assert _dim(score, "progress_integrity").value is None
        assert _dim(score, "staleness_health").value is None
        assert _dim(score, "duplication_health").value is None
        assert score.total == pytest.approx(0.15 / 0.50)
        assert score.total != pytest.approx(0.65)

    def test_total_score_skips_null_dimensions(self) -> None:
        measured = DimensionScore(
            name="ac_validity", value=1.0, numerator=1, denominator=1, weight=0.15
        )
        also_measured = DimensionScore(
            name="duplication_health", value=1.0, numerator=1, denominator=1, weight=0.15
        )
        nulls = [
            DimensionScore(
                name=name, value=None, numerator=0, denominator=0,
                weight=0.20, excluded_reason="unmeasurable",
            )
            for name in ("progress_integrity", "done_integrity", "staleness_health")
        ]
        policy = load_policy()
        assert total_score([measured, also_measured, *nulls], policy) == pytest.approx(1.0)

    def test_all_null_totals_zero(self) -> None:
        nulls = [
            DimensionScore(
                name=name, value=None, numerator=0, denominator=0,
                weight=0.15, excluded_reason="unmeasurable",
            )
            for name in DIMENSION_ORDER
        ]
        assert total_score(nulls, load_policy()) == 0.0


class TestFractionRendering:
    def test_measured_dimensions_render_numerator_over_denominator(self) -> None:
        policy = load_policy()
        t = ticket(
            "AUTO-1",
            status="In Progress",
            branch="feature/AUTO-1",
            status_changed_at=days_ago(1),
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        from factories import commit

        r = repo([branch("feature/AUTO-1", [commit("a" * 40, 1)])])
        rendered = render_score(compute_score(board([t]), r, frozen_clock()))

        assert f"ac_validity" in rendered and "1/1" in rendered
        assert f"1/1" in rendered.split("progress_integrity")[1].split("\n")[0]
        staleness_line = next(
            line for line in rendered.splitlines() if line.strip().startswith("staleness_health")
        )
        assert f"{policy.stale_day_cap - 1}/{policy.stale_day_cap} ticket-days" in staleness_line
        duplication_line = next(
            line for line in rendered.splitlines() if line.strip().startswith("duplication_health")
        )
        assert "1/1 tickets" in duplication_line


class TestEvidenceLogExclusions:
    def test_evidence_log_marks_excluded_dimensions(self, tmp_path) -> None:
        done = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        r = repo([branch("feature/AUTO-1", [])])
        score = compute_score(board([done]), r, frozen_clock())

        path = write_evidence_log(tmp_path, score, run_id="run-test")
        text = path.read_text(encoding="utf-8")

        assert "## progress_integrity - EXCLUDED (no In Progress tickets)" in text
        assert "## staleness_health - EXCLUDED (no active tickets)" in text
        assert "## done_integrity - 0/1" in text
        assert "- run: run-test" in text
        assert "\r" not in text  # LF-only, stable across platforms

    def test_measured_dimensions_itemise_every_point(self, tmp_path) -> None:
        done, r = _done_ticket_with_proof()
        score = compute_score(board([done]), r, frozen_clock())
        path = write_evidence_log(tmp_path, score)
        text = path.read_text(encoding="utf-8")

        # done_integrity: the PR proof and the green CI proof, itemised.
        assert "## done_integrity - 1/1" in text
        assert "[pass] pr 3 " in text
        assert "[pass] check_run" in text
        # ac_validity carries one line per ticket with a verdict.
        assert "[pass] jira_changelog AUTO-1" in text
