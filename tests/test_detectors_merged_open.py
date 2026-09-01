"""MERGED_PR_TICKET_OPEN: the PR says the work shipped; the board never noticed.

Fires for a merged PR whose head branch maps to a ticket that is not
Done/Resolved. Closed (never merged) and still-open PRs prove nothing.
"""

from __future__ import annotations

from factories import (
    board,
    branch,
    commit,
    days_ago,
    frozen_clock,
    merged_pr,
    repo,
    ticket,
)

from groundtruth.contracts.board import RepoPullRequest
from groundtruth.contracts.discrepancy import (
    ActionVerb,
    DiscrepancySeverity,
    DiscrepancyType,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.merged_open import detect_merged_pr_ticket_open

HEAD = "feature/AUTO-1"


def _open_ticket(key: str = "AUTO-1", **overrides):
    fields = dict(key=key, status="In Progress", branch=HEAD)
    fields.update(overrides)
    return ticket(**fields)


class TestMergedPrTicketOpenFires:
    def test_merged_pr_with_in_progress_ticket(self) -> None:
        t = _open_ticket()
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [merged_pr(7, HEAD)])
        found = detect_merged_pr_ticket_open(board([t]), r, frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.MERGED_PR_TICKET_OPEN
        assert d.severity is DiscrepancySeverity.HIGH
        assert d.subject == "AUTO-1"
        assert d.evidence, "a discrepancy without evidence is a claim without proof"
        assert [e.kind for e in d.evidence] == [EvidenceKind.PR, EvidenceKind.JIRA_CHANGELOG]
        pr_evidence = d.evidence[0]
        assert pr_evidence.ref == "7"
        assert pr_evidence.url == "https://github.com/acme/repo/pull/7"
        assert pr_evidence.detail["head"] == HEAD
        assert pr_evidence.detail["base"] == "main"
        assert d.evidence[1].detail["status"] == "In Progress"

    def test_proposed_action_transitions_to_done(self) -> None:
        t = _open_ticket()
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [merged_pr(7, HEAD)])
        found = detect_merged_pr_ticket_open(board([t]), r, frozen_clock())
        action = found[0].proposed_action
        assert action.verb is ActionVerb.TRANSITION
        assert action.target == "AUTO-1"
        assert action.params["to"] == "Done"

    def test_merged_at_without_state_field_counts_as_merged(self) -> None:
        # A merge timestamp is the proof; the state string is a convenience.
        t = _open_ticket()
        pr = RepoPullRequest(
            number=7,
            state="OPEN",
            head_ref=HEAD,
            base_ref="main",
            merged_at=days_ago(1),
            merge_sha="b" * 40,
        )
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [pr])
        assert len(detect_merged_pr_ticket_open(board([t]), r, frozen_clock())) == 1

    def test_ticket_matched_by_key_in_branch_path(self) -> None:
        # No explicit branch link; the key inside the path still maps.
        t = ticket("AUTO-9", status="In Progress")  # branch=None
        head = "feature/AUTO-9/login"
        r = repo([branch(head, [commit("a" * 40, 2)])], [merged_pr(11, head)])
        found = detect_merged_pr_ticket_open(board([t]), r, frozen_clock())
        assert [d.subject for d in found] == ["AUTO-9"]


class TestMergedPrTicketOpenSkips:
    def test_done_ticket_is_not_flagged(self) -> None:
        t = _open_ticket(status="Done")
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [merged_pr(7, HEAD)])
        assert detect_merged_pr_ticket_open(board([t]), r, frozen_clock()) == []

    def test_resolved_ticket_is_not_flagged(self) -> None:
        t = _open_ticket(status="Resolved")
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [merged_pr(7, HEAD)])
        assert detect_merged_pr_ticket_open(board([t]), r, frozen_clock()) == []

    def test_closed_pr_is_not_flagged(self) -> None:
        t = _open_ticket()
        pr = RepoPullRequest(
            number=7, state="CLOSED", head_ref=HEAD, base_ref="main"
        )
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [pr])
        assert detect_merged_pr_ticket_open(board([t]), r, frozen_clock()) == []

    def test_open_pr_is_not_flagged(self) -> None:
        t = _open_ticket()
        pr = RepoPullRequest(
            number=7, state="OPEN", head_ref=HEAD, base_ref="main"
        )
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [pr])
        assert detect_merged_pr_ticket_open(board([t]), r, frozen_clock()) == []

    def test_pr_for_unmapped_branch_is_ignored(self) -> None:
        # No ticket claims this head; that is ORPHAN_BRANCH territory.
        t = _open_ticket()
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [merged_pr(7, "feature/NOPE")])
        assert detect_merged_pr_ticket_open(board([t]), r, frozen_clock()) == []

    def test_control_ticket_is_not_flagged(self) -> None:
        t = _open_ticket(is_control=True)
        r = repo([branch(HEAD, [commit("a" * 40, 2)])], [merged_pr(7, HEAD)])
        assert detect_merged_pr_ticket_open(board([t]), r, frozen_clock()) == []
