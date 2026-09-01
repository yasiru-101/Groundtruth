"""DUPLICATE_SUSPECTED: near-duplicate active tickets, proposal only.

Deterministic token-set Jaccard over summaries (plural-folded, stopwords
and short tokens dropped) at the frozen 0.45 threshold. Suspects are
PROPOSED, never auto-resolved — closing a duplicate is a human decision.
"""

from __future__ import annotations

from factories import board, frozen_clock, repo, ticket

from groundtruth.contracts.discrepancy import (
    ActionVerb,
    DiscrepancySeverity,
    DiscrepancyType,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.duplicate import detect_duplicate, jaccard, tokens
from groundtruth.scoring.policy import load_policy


class TestTokenizer:
    def test_plural_folding_and_stopwords(self) -> None:
        # "timeouts" -> "timeout", "keys" -> "key"; the/and dropped.
        got = tokens("The timeouts and API keys", 3)
        assert got == {"timeout", "api", "key"}

    def test_short_tokens_are_dropped(self) -> None:
        assert tokens("to be or a game", 3) == {"game"}

    def test_tokens_are_lowercased(self) -> None:
        assert tokens("Login TIMEOUT", 3) == {"login", "timeout"}

    def test_jaccard_extremes(self) -> None:
        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
        assert jaccard({"a"}, {"b"}) == 0.0
        assert jaccard(set(), {"a"}) == 0.0


class TestDuplicateSuspectedFires:
    def test_near_identical_active_pair_is_proposed(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        found = detect_duplicate(board([t1, t2]), repo(), frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.DUPLICATE_SUSPECTED
        assert d.severity is DiscrepancySeverity.LOW
        assert d.subject == "AUTO-1+AUTO-2"
        assert d.evidence, "a discrepancy without evidence is a claim without proof"
        assert [e.kind for e in d.evidence] == [
            EvidenceKind.JIRA_CHANGELOG,
            EvidenceKind.JIRA_CHANGELOG,
        ]
        assert [e.ref for e in d.evidence] == ["AUTO-1", "AUTO-2"]
        assert d.evidence[0].detail["method"] == "token-set jaccard (plural-folded)"
        assert d.evidence[0].detail["similarity"] == "1.000"

    def test_proposal_is_never_auto_resolved(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        found = detect_duplicate(board([t1, t2]), repo(), frozen_clock())
        action = found[0].proposed_action
        assert action.verb is ActionVerb.CLOSE_DUPLICATE
        assert action.target == "AUTO-2"
        assert action.params["duplicate_of"] == "AUTO-1"
        assert action.requires_approval is True

    def test_similarity_exactly_at_threshold_fires(self) -> None:
        # 9 shared tokens over a 20-token union == the frozen 0.45 threshold.
        shared = [f"word{i}" for i in range(9)]
        only_a = [f"alpha{i}" for i in range(5)]
        only_b = [f"beta{i}" for i in range(6)]
        s1 = " ".join(shared + only_a)
        s2 = " ".join(shared + only_b)
        assert jaccard(tokens(s1, 3), tokens(s2, 3)) == load_policy().duplicate_threshold
        t1 = ticket("AUTO-1", summary=s1)
        t2 = ticket("AUTO-2", summary=s2)
        assert len(detect_duplicate(board([t1, t2]), repo(), frozen_clock())) == 1

    def test_three_identical_tickets_yield_three_pairs(self) -> None:
        tickets = [
            ticket("AUTO-1", summary="Fix login timeout on checkout"),
            ticket("AUTO-2", summary="Fix login timeout on checkout"),
            ticket("AUTO-3", summary="Fix login timeout on checkout"),
        ]
        found = detect_duplicate(board(tickets), repo(), frozen_clock())
        assert [d.subject for d in found] == [
            "AUTO-1+AUTO-2",
            "AUTO-1+AUTO-3",
            "AUTO-2+AUTO-3",
        ]

    def test_detection_is_deterministic(self) -> None:
        tickets = [
            ticket("AUTO-1", summary="Fix login timeout on checkout"),
            ticket("AUTO-2", summary="Fix login timeouts in checkout"),
        ]
        first = detect_duplicate(board(tickets), repo(), frozen_clock())
        second = detect_duplicate(board(tickets), repo(), frozen_clock())
        assert [d.discrepancy_id for d in first] == [d.discrepancy_id for d in second]


class TestDuplicateSuspectedSkips:
    def test_dissimilar_pair_is_not_flagged(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Add dark mode color theme")
        assert detect_duplicate(board([t1, t2]), repo(), frozen_clock()) == []

    def test_similarity_just_below_threshold_does_not_fire(self) -> None:
        # 8 shared tokens over a 21-token union < 0.45.
        shared = [f"word{i}" for i in range(8)]
        only_a = [f"alpha{i}" for i in range(6)]
        only_b = [f"beta{i}" for i in range(7)]
        t1 = ticket("AUTO-1", summary=" ".join(shared + only_a))
        t2 = ticket("AUTO-2", summary=" ".join(shared + only_b))
        assert detect_duplicate(board([t1, t2]), repo(), frozen_clock()) == []

    def test_terminal_ticket_is_not_a_candidate(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout", status="Done")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        assert detect_duplicate(board([t1, t2]), repo(), frozen_clock()) == []

    def test_control_ticket_is_not_a_candidate(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout", is_control=True)
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        assert detect_duplicate(board([t1, t2]), repo(), frozen_clock()) == []
