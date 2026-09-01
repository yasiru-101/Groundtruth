"""ORPHAN_BRANCH: real commits exist for work no ticket knows about.

Fires for a non-base branch with at least one commit that maps to no
ticket (by branch link or by ticket key inside the branch path).
"""

from __future__ import annotations

from factories import board, branch, commit, frozen_clock, repo, ticket

from groundtruth.contracts.discrepancy import (
    ActionVerb,
    DiscrepancySeverity,
    DiscrepancyType,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.orphan_branch import detect_orphan_branch


class TestOrphanBranchFires:
    def test_branch_with_commits_and_no_ticket(self) -> None:
        r = repo([branch("feature/orphan", [commit("a" * 40, 3, "orphan work")])])
        found = detect_orphan_branch(board(), r, frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.ORPHAN_BRANCH
        assert d.severity is DiscrepancySeverity.LOW
        assert d.subject == "feature/orphan"
        assert d.evidence, "a discrepancy without evidence is a claim without proof"
        assert [e.kind for e in d.evidence] == [EvidenceKind.BRANCH, EvidenceKind.COMMIT]
        assert d.evidence[0].detail["commits"] == "1"
        assert d.evidence[0].detail["tip"] == "a" * 40
        assert d.evidence[1].ref == "a" * 40
        assert d.evidence[1].detail["subject"] == "orphan work"

    def test_proposed_action_creates_a_ticket_for_the_branch(self) -> None:
        r = repo([branch("feature/orphan", [commit("a" * 40, 3)])])
        found = detect_orphan_branch(board(), r, frozen_clock())
        action = found[0].proposed_action
        assert action.verb is ActionVerb.CREATE_TICKET
        assert action.target == "feature/orphan"

    def test_multiple_orphans_sorted_by_branch_name(self) -> None:
        r = repo(
            [
                branch("feature/zed", [commit("c" * 40, 3)]),
                branch("feature/alpha", [commit("a" * 40, 3)]),
            ]
        )
        found = detect_orphan_branch(board(), r, frozen_clock())
        assert [d.subject for d in found] == ["feature/alpha", "feature/zed"]


class TestOrphanBranchSkips:
    def test_branch_linked_to_a_ticket(self) -> None:
        t = ticket("AUTO-1", status="In Progress", branch="feature/AUTO-1")
        r = repo([branch("feature/AUTO-1", [commit("a" * 40, 3)])])
        assert detect_orphan_branch(board([t]), r, frozen_clock()) == []

    def test_base_branch_is_never_an_orphan(self) -> None:
        r = repo([branch("main", [commit("a" * 40, 3)])])
        assert detect_orphan_branch(board(), r, frozen_clock()) == []

    def test_branch_matched_by_ticket_key_in_path(self) -> None:
        t = ticket("AUTO-9", status="To Do")  # no explicit branch link
        r = repo([branch("feature/AUTO-9/login", [commit("a" * 40, 3)])])
        assert detect_orphan_branch(board([t]), r, frozen_clock()) == []

    def test_branch_matched_case_insensitively(self) -> None:
        t = ticket("AUTO-1", status="To Do", branch="feature/auto-1")
        r = repo([branch("feature/AUTO-1", [commit("a" * 40, 3)])])
        assert detect_orphan_branch(board([t]), r, frozen_clock()) == []

    def test_branch_with_no_commits_is_ignored(self) -> None:
        r = repo([branch("feature/empty", [])])
        assert detect_orphan_branch(board(), r, frozen_clock()) == []
