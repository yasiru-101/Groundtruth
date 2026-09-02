"""Intake idempotency: the same source document must not create duplicate tickets.

Idempotency is enforced by two independent mechanisms:

1. A Jira label ``gt-idem-<hash>`` written on every intake-created issue.
2. A local ``intake_state.json`` mapping the same hash to the created key.

Either one is sufficient to skip a previously accepted story.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from groundtruth.agents.intake import IntakeAgent
from groundtruth.config import Settings
from groundtruth.contracts.ledger import ApprovalRef
from groundtruth.contracts.story import AcceptanceCriterion, ProvenanceRef, Story
from groundtruth.safety.approval import ChangeItem, ChangeSet


def _make_story() -> Story:
    return Story(
        idempotency_key="idem-abc",
        summary="Add retry logic to checkout",
        description="Checkout intermittently fails under load.",
        acceptance_criteria=[
            AcceptanceCriterion(
                ac_id="AC1",
                given="a payment fails transiently",
                when="the checkout service retries",
                then="the order completes successfully",
                raw="Given a payment fails transiently When the checkout service retries Then the order completes successfully",
                is_wellformed=True,
            )
        ],
        points=3,
        components=["checkout"],
        source=ProvenanceRef(doc_id="notes.md", llm_call_id="call-1"),
    )


def _make_agent(tmp_path, jira=None, llm=None, steward=None) -> IntakeAgent:
    settings = Settings(
        jira_project_key="AUTO",
        artifacts_dir=tmp_path,
    )
    return IntakeAgent(
        settings=settings,
        jira=jira or MagicMock(),
        llm=llm or MagicMock(),
        steward=steward,
        state_path=tmp_path / "intake_state.json",
    )


def _changeset(story: Story) -> ChangeSet:
    return ChangeSet(
        items=[
            ChangeItem(
                action="intake.create_ticket",
                subject=story.idempotency_key,
                params={"story": story.model_dump(mode="json")},
            )
        ],
        created_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )


def _approval() -> ApprovalRef:
    return ApprovalRef(
        changeset_hash="cs-abc",
        approved_by="operator:test",
        approved_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
    )


class TestIntakeIdempotency:
    def test_first_apply_creates_ticket_and_writes_local_state(self, tmp_path) -> None:
        jira = MagicMock()
        jira.search.return_value = []
        jira.create_issue.return_value = {"key": "AUTO-99"}
        jira.add_comment.return_value = None

        story = _make_story()
        agent = _make_agent(tmp_path, jira=jira)
        created = agent.apply(_changeset(story), _approval())

        assert [s.jira_key for s in created] == ["AUTO-99"]
        jira.create_issue.assert_called_once()
        labels = jira.create_issue.call_args[0][0]["labels"]
        assert "gt-idem" in labels
        assert f"gt-idem-{story.idempotency_key}" in labels
        assert "gt-points-3" in labels
        assert "gt-component-checkout" in labels

        state = agent._load_state()
        assert state[story.idempotency_key]["jira_key"] == "AUTO-99"

    def test_second_apply_skips_when_jira_label_exists(self, tmp_path) -> None:
        jira = MagicMock()
        jira.search.return_value = [
            {
                "key": "AUTO-99",
                "fields": {
                    "labels": ["gt-idem", "gt-idem-idem-abc"],
                },
            }
        ]
        story = _make_story()
        agent = _make_agent(tmp_path, jira=jira)

        created = agent.apply(_changeset(story), _approval())

        assert created == []
        jira.create_issue.assert_not_called()

    def test_second_apply_skips_when_local_state_exists(self, tmp_path) -> None:
        jira = MagicMock()
        jira.search.side_effect = RuntimeError("network unavailable")
        jira.create_issue.return_value = {"key": "AUTO-99"}

        story = _make_story()
        agent = _make_agent(tmp_path, jira=jira)
        # Seed local state as if a previous run already created the ticket.
        agent._save_state(
            {
                story.idempotency_key: {
                    "jira_key": "AUTO-99",
                    "summary": story.summary,
                    "points": story.points,
                    "components": story.components,
                    "depends_on": [],
                }
            }
        )

        created = agent.apply(_changeset(story), _approval())

        assert created == []
        jira.create_issue.assert_not_called()


class TestExistingByIdem:
    def test_maps_labels_to_idempotency_keys(self, tmp_path) -> None:
        jira = MagicMock()
        jira.search.return_value = [
            {
                "key": "AUTO-10",
                "fields": {"labels": ["gt-idem", "gt-idem-key-one"]},
            },
            {
                "key": "AUTO-11",
                "fields": {"labels": ["gt-idem", "gt-idem-key-two", "other"]},
            },
        ]
        agent = _make_agent(tmp_path, jira=jira)

        mapping = agent._existing_by_idem("AUTO")

        assert mapping == {
            "key-one": "AUTO-10",
            "key-two": "AUTO-11",
        }
        jira.search.assert_called_once()
        assert 'labels = "gt-idem"' in jira.search.call_args[0][0]

    def test_returns_empty_mapping_when_search_fails(self, tmp_path) -> None:
        jira = MagicMock()
        jira.search.side_effect = RuntimeError("auth failed")
        agent = _make_agent(tmp_path, jira=jira)

        assert agent._existing_by_idem("AUTO") == {}
