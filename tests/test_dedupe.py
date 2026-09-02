"""Intake duplicate detection against the live board.

A new story whose summary is token-set-similar to an active existing ticket
becomes a ``DUPLICATE_SUSPECTED`` discrepancy. The story itself is tagged
with a ``DedupeVerdict`` for later human confirmation; it is never
auto-resolved.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from groundtruth.agents.intake import IntakeAgent
from groundtruth.clock import FrozenClock
from groundtruth.config import Settings
from groundtruth.contracts.discrepancy import DiscrepancyType
from groundtruth.contracts.story import AcceptanceCriterion, Story
from tests.factories import AS_OF, board, repo, ticket


def _agent(steward_board, steward_repo=None):
    settings = Settings(jira_project_key="AUTO")
    steward = SimpleNamespace(collect=lambda: (steward_board, steward_repo or repo()))
    return IntakeAgent(
        settings=settings,
        jira=MagicMock(),
        llm=MagicMock(),
        steward=steward,
        clock=FrozenClock(AS_OF),
    )


def _story(summary: str) -> Story:
    return Story(
        idempotency_key=f"idem-{summary.replace(' ', '-')}",
        summary=summary,
        acceptance_criteria=[
            AcceptanceCriterion(
                ac_id="AC1",
                given="x",
                when="y",
                then="z",
                raw="Given x When y Then z",
                is_wellformed=True,
            )
        ],
        points=3,
        components=["api"],
    )


class TestIntakeDedupe:
    def test_near_duplicate_active_ticket_is_suspected(self) -> None:
        existing = ticket("AUTO-1", summary="Fix login timeout on checkout")
        story = _story("Fix login timeouts in checkout")
        agent = _agent(board([existing]))

        discrepancies = agent._detect_duplicates([story], "notes.md")

        assert len(discrepancies) == 1
        d = discrepancies[0]
        assert d.type is DiscrepancyType.DUPLICATE_SUSPECTED
        assert "AUTO-1" in d.subject
        assert d.proposed_action.requires_approval is True

        assert story.dedupe is not None
        assert story.dedupe.candidate_jira_keys == ["AUTO-1"]
        assert story.dedupe.similarity >= 0.45
        assert story.dedupe.human_confirmed is None

    def test_dissimilar_story_is_not_flagged(self) -> None:
        existing = ticket("AUTO-1", summary="Fix login timeout on checkout")
        story = _story("Add dark mode color theme")
        agent = _agent(board([existing]))

        assert agent._detect_duplicates([story], "notes.md") == []
        assert story.dedupe is None

    def test_terminal_ticket_is_not_a_candidate(self) -> None:
        existing = ticket(
            "AUTO-1", summary="Fix login timeout on checkout", status="Done"
        )
        story = _story("Fix login timeouts in checkout")
        agent = _agent(board([existing]))

        assert agent._detect_duplicates([story], "notes.md") == []

    def test_control_ticket_is_not_a_candidate(self) -> None:
        existing = ticket(
            "AUTO-1",
            summary="Fix login timeout on checkout",
            is_control=True,
        )
        story = _story("Fix login timeouts in checkout")
        agent = _agent(board([existing]))

        assert agent._detect_duplicates([story], "notes.md") == []

    def test_multiple_existing_tickets_picks_best_match(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Add dark mode color theme")
        story = _story("Fix login timeouts in checkout")
        agent = _agent(board([t1, t2]))

        discrepancies = agent._detect_duplicates([story], "notes.md")
        assert len(discrepancies) == 1
        assert "AUTO-1" in discrepancies[0].subject
