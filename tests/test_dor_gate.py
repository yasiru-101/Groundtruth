"""Definition-of-Ready gating for intake stories.

The DoR gate is deterministic and machine-readable: every refused story
carries one or more failure codes from ``DoRFailureCode``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from groundtruth.agents.intake import IntakeAgent
from groundtruth.config import Settings
from groundtruth.contracts.story import (
    AcceptanceCriterion,
    DoRFailureCode,
    Story,
)


def _agent() -> IntakeAgent:
    settings = Settings(jira_project_key="AUTO")
    return IntakeAgent(
        settings=settings,
        jira=MagicMock(),
        llm=MagicMock(),
    )


def _story(
    *,
    summary: str = "A valid story",
    ac: list[AcceptanceCriterion] | None = None,
    points: int | None = 3,
    components: list[str] | None = None,
    depends_on: list[str] | None = None,
) -> Story:
    return Story(
        idempotency_key=f"idem-{summary}",
        summary=summary,
        acceptance_criteria=[_well_formed_ac()] if ac is None else ac,
        points=points,
        components=["api"] if components is None else components,
        depends_on=[] if depends_on is None else depends_on,
    )


def _well_formed_ac() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        ac_id="AC1",
        given="the system is online",
        when="a request arrives",
        then="it is processed",
        raw="Given the system is online When a request arrives Then it is processed",
        is_wellformed=True,
    )


def _malformed_ac() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        ac_id="AC1",
        given="",
        when="",
        then="",
        raw="",
        is_wellformed=False,
    )


class TestDoRGateAccepts:
    def test_valid_story_passes(self) -> None:
        story = _story()
        accepted, refused = _agent()._apply_dor_gate([story])
        assert accepted == [story]
        assert refused == []
        assert story.dor is not None
        assert story.dor.passed is True
        assert story.dor.failures == []


class TestDoRGateRefuses:
    def test_missing_acceptance_criteria(self) -> None:
        story = _story(ac=[], summary="no ac")
        _, refused = _agent()._apply_dor_gate([story])
        assert len(refused) == 1
        assert DoRFailureCode.NO_AC.value in refused[0].dor.failures

    def test_malformed_acceptance_criteria(self) -> None:
        story = _story(ac=[_malformed_ac()], summary="malformed ac")
        _, refused = _agent()._apply_dor_gate([story])
        assert DoRFailureCode.AC_MALFORMED.value in refused[0].dor.failures

    def test_missing_points(self) -> None:
        story = _story(points=None, summary="no points")
        _, refused = _agent()._apply_dor_gate([story])
        assert DoRFailureCode.NO_POINTS.value in refused[0].dor.failures

    def test_invalid_points(self) -> None:
        story = _story(points=4, summary="invalid points")
        _, refused = _agent()._apply_dor_gate([story])
        assert DoRFailureCode.NO_POINTS.value in refused[0].dor.failures

    def test_missing_components(self) -> None:
        story = _story(components=[], summary="no component")
        _, refused = _agent()._apply_dor_gate([story])
        assert DoRFailureCode.NO_COMPONENT.value in refused[0].dor.failures

    def test_circular_dependency(self) -> None:
        a = _story(summary="A", depends_on=["B"])
        b = _story(summary="B", depends_on=["A"])
        _, refused = _agent()._apply_dor_gate([a, b])
        assert len(refused) == 2
        assert all(
            DoRFailureCode.CIRCULAR_DEP.value in s.dor.failures for s in refused
        )

    def test_multiple_failures_reported_together(self) -> None:
        story = _story(
            ac=[], points=None, components=[], summary="multiple failures"
        )
        _, refused = _agent()._apply_dor_gate([story])
        failures = refused[0].dor.failures
        assert DoRFailureCode.NO_AC.value in failures
        assert DoRFailureCode.NO_POINTS.value in failures
        assert DoRFailureCode.NO_COMPONENT.value in failures
