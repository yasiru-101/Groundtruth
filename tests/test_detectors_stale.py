"""STALE_IN_PROGRESS: the ticket says work is happening; the branch disagrees.

Fires for an In Progress ticket with a linked branch whose newest commit is
older than the staleness window (7 days, frozen policy) or whose branch is
missing from the repo entirely. Branchless In Progress tickets are skipped
here — nothing is claiming progress — their status age is scored by the
staleness_health dimension instead.
"""

from __future__ import annotations

from factories import (
    branch,
    board,
    commit,
    days_ago,
    frozen_clock,
    repo,
    ticket,
)

from groundtruth.contracts.discrepancy import (
    ActionVerb,
    DiscrepancySeverity,
    DiscrepancyType,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.stale import detect_stale

BRANCH_NAME = "feature/AUTO-1"


def _in_progress(key: str = "AUTO-1", br: str = BRANCH_NAME):
    return ticket(
        key,
        status="In Progress",
        branch=br,
        status_changed_at=days_ago(30),
    )


class TestStaleFires:
    def test_commit_older_than_window_is_stale(self) -> None:
        t = _in_progress()
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 8)])])
        found = detect_stale(board([t]), r, frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.STALE_IN_PROGRESS
        assert d.severity is DiscrepancySeverity.MEDIUM
        assert d.subject == "AUTO-1"
        assert d.proposed_action.verb is ActionVerb.COMMENT
        assert d.proposed_action.target == "AUTO-1"
        assert d.evidence, "a discrepancy without evidence is a claim without proof"
        assert [e.kind for e in d.evidence] == [
            EvidenceKind.JIRA_CHANGELOG,
            EvidenceKind.COMMIT,
        ]
        commit_evidence = d.evidence[1]
        assert commit_evidence.ref == "a" * 40
        assert commit_evidence.detail["age_days"] == "8"
        assert commit_evidence.detail["window_days"] == "7"
        assert commit_evidence.detail["branch"] == BRANCH_NAME

    def test_missing_branch_is_stale(self) -> None:
        t = _in_progress()
        r = repo()  # no branches at all
        found = detect_stale(board([t]), r, frozen_clock())

        assert len(found) == 1
        assert [e.kind for e in found[0].evidence] == [
            EvidenceKind.JIRA_CHANGELOG,
            EvidenceKind.BRANCH,
        ]
        branch_evidence = found[0].evidence[1]
        assert branch_evidence.ref == BRANCH_NAME
        assert branch_evidence.detail["found_in_repo"] == "no"

    def test_branch_with_no_commits_is_stale(self) -> None:
        t = _in_progress()
        r = repo([branch(BRANCH_NAME, [])])
        found = detect_stale(board([t]), r, frozen_clock())
        assert len(found) == 1
        assert found[0].evidence[1].kind is EvidenceKind.BRANCH

    def test_multiple_stale_tickets_one_discrepancy_each(self) -> None:
        tickets = [
            _in_progress("AUTO-1", "feature/AUTO-1"),
            _in_progress("AUTO-2", "feature/AUTO-2"),
        ]
        r = repo(
            [
                branch("feature/AUTO-1", [commit("a" * 40, 30)]),
                branch("feature/AUTO-2", [commit("b" * 40, 30)]),
            ]
        )
        found = detect_stale(board(tickets), r, frozen_clock())
        assert [d.subject for d in found] == ["AUTO-1", "AUTO-2"]


class TestStaleSkips:
    def test_commit_exactly_at_window_is_not_stale(self) -> None:
        t = _in_progress()
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 7)])])
        assert detect_stale(board([t]), r, frozen_clock()) == []

    def test_fresh_commit_is_not_stale(self) -> None:
        t = _in_progress()
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 1)])])
        assert detect_stale(board([t]), r, frozen_clock()) == []

    def test_branchless_in_progress_is_skipped(self) -> None:
        t = _in_progress()
        t.branch = None
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 30)])])
        assert detect_stale(board([t]), r, frozen_clock()) == []

    def test_todo_ticket_with_stale_branch_is_skipped(self) -> None:
        t = ticket("AUTO-1", status="To Do", branch=BRANCH_NAME)
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 30)])])
        assert detect_stale(board([t]), r, frozen_clock()) == []

    def test_done_ticket_with_stale_branch_is_skipped(self) -> None:
        t = ticket("AUTO-1", status="Done", branch=BRANCH_NAME)
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 30)])])
        assert detect_stale(board([t]), r, frozen_clock()) == []

    def test_control_ticket_is_skipped(self) -> None:
        t = _in_progress()
        t.is_control = True
        r = repo([branch(BRANCH_NAME, [commit("a" * 40, 30)])])
        assert detect_stale(board([t]), r, frozen_clock()) == []
