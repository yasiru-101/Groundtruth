"""PlannerAgent: deterministic sprint planning from board + local state.

The planner is read-only: it computes velocity from recent Done tickets,
topologically orders candidates by local-only dependencies, assigns load
across assignees, and reports over-commitment. It never writes to Jira or
git.
"""

from __future__ import annotations

import json

import pytest

from groundtruth.agents.planner import PlannerAgent, PlannerError
from groundtruth.clock import FrozenClock
from groundtruth.contracts.board import BoardTicket
from tests.factories import AS_OF, board, days_ago, frozen_clock, repo, ticket


def _planner(
    tmp_path,
    tickets,
    *,
    capacity: int | None = None,
    assignees: list[str] | None = None,
    intake_state: dict | None = None,
):
    state_path = tmp_path / "intake_state.json"
    if intake_state is not None:
        state_path.write_text(json.dumps(intake_state, indent=2), encoding="utf-8")
    return PlannerAgent(
        board=board(tickets),
        repo=repo(),
        clock=frozen_clock(),
        capacity=capacity,
        assignees=assignees,
        intake_state_path=state_path,
    )


class TestPlannerBasics:
    def test_empty_board_yields_zero_velocity_and_empty_plan(self, tmp_path) -> None:
        plan = _planner(tmp_path, []).build_plan()

        assert plan.project_key == "AUTO"
        assert plan.velocity == 0
        assert plan.capacity == 0
        assert plan.total_candidate_points == 0
        assert plan.total_selected_points == 0
        assert plan.selected == []
        assert plan.unscheduled == []
        assert plan.over_committed is False

    def test_velocity_from_recent_done_tickets(self, tmp_path) -> None:
        tickets = [
            ticket(
                "AUTO-1",
                status="Done",
                points=5,
                status_changed_at=days_ago(5),
            ),
            ticket(
                "AUTO-2",
                status="Done",
                points=3,
                status_changed_at=days_ago(10),
            ),
            # Outside the 30-day window.
            ticket(
                "AUTO-3",
                status="Done",
                points=8,
                status_changed_at=days_ago(31),
            ),
        ]
        plan = _planner(tmp_path, tickets).build_plan()
        assert plan.velocity == 8
        assert plan.capacity == 8

    def test_capacity_override(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="Done", points=5, status_changed_at=days_ago(1)),
        ]
        plan = _planner(tmp_path, tickets, capacity=13).build_plan()
        assert plan.capacity == 13
        assert plan.velocity == 5


class TestPlannerSelection:
    def test_selects_active_pointed_tickets(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=3),
            ticket("AUTO-2", status="In Progress", points=5),
        ]
        plan = _planner(tmp_path, tickets, capacity=20).build_plan()
        assert plan.total_candidate_points == 8
        assert plan.total_selected_points == 8
        assert {t.key for t in plan.selected} == {"AUTO-1", "AUTO-2"}

    def test_skips_done_control_and_unpointed_tickets(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=3),
            ticket("AUTO-2", status="Done", points=5),
            ticket("AUTO-3", status="To Do", points=2, is_control=True),
            ticket("AUTO-4", status="To Do"),  # no points
        ]
        plan = _planner(tmp_path, tickets, capacity=20).build_plan()
        assert plan.total_candidate_points == 3
        assert {t.key for t in plan.selected} == {"AUTO-1"}

    def test_capacity_exceeded_flags_over_committed(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=5),
            ticket("AUTO-2", status="To Do", points=5),
            ticket("AUTO-3", status="To Do", points=5),
        ]
        plan = _planner(tmp_path, tickets, capacity=10).build_plan()
        assert plan.over_committed is True
        assert plan.total_selected_points == 10
        assert len(plan.selected) == 2
        assert len(plan.unscheduled) == 1


class TestPlannerDependencies:
    def test_topological_order_respects_dependencies(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=3),
            ticket("AUTO-2", status="To Do", points=5),
        ]
        intake_state = {
            "idem-2": {
                "jira_key": "AUTO-2",
                "summary": "Second",
                "points": 5,
                "components": [],
                "depends_on": ["AUTO-1"],
            }
        }
        plan = _planner(tmp_path, tickets, capacity=20, intake_state=intake_state).build_plan()
        keys = [t.key for t in plan.selected]
        assert keys.index("AUTO-1") < keys.index("AUTO-2")

    def test_unmet_dependency_makes_ticket_unscheduled(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=3),
            ticket("AUTO-2", status="To Do", points=5),
        ]
        intake_state = {
            "idem-2": {
                "jira_key": "AUTO-2",
                "summary": "Second",
                "points": 5,
                "components": [],
                "depends_on": ["AUTO-99"],  # not a candidate
            }
        }
        plan = _planner(tmp_path, tickets, capacity=20, intake_state=intake_state).build_plan()
        assert {t.key for t in plan.selected} == {"AUTO-1"}
        assert {t.key for t in plan.unscheduled} == {"AUTO-2"}

    def test_cycle_is_reported_and_blocks_selection(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=3),
            ticket("AUTO-2", status="To Do", points=5),
        ]
        intake_state = {
            "idem-1": {
                "jira_key": "AUTO-1",
                "summary": "First",
                "points": 3,
                "components": [],
                "depends_on": ["AUTO-2"],
            },
            "idem-2": {
                "jira_key": "AUTO-2",
                "summary": "Second",
                "points": 5,
                "components": [],
                "depends_on": ["AUTO-1"],
            },
        }
        plan = _planner(tmp_path, tickets, capacity=20, intake_state=intake_state).build_plan()
        assert len(plan.cycles) == 1
        cycle = plan.cycles[0]
        assert set(cycle) == {"AUTO-1", "AUTO-2"}
        # Tickets in a cycle cannot have their dependencies satisfied first.
        assert {t.key for t in plan.unscheduled} == {"AUTO-1", "AUTO-2"}
        assert plan.selected == []


class TestPlannerAssignments:
    def test_load_balancing_across_assignees(self, tmp_path) -> None:
        tickets = [
            ticket("AUTO-1", status="To Do", points=5),
            ticket("AUTO-2", status="To Do", points=3),
            ticket("AUTO-3", status="To Do", points=2),
        ]
        plan = _planner(
            tmp_path, tickets, capacity=20, assignees=["alice", "bob"]
        ).build_plan()
        assert set(plan.assignments.keys()) == {"alice", "bob"}
        by_key = {t.key: t.assignee for t in plan.selected}
        # Alice gets first ticket; bob gets second; third goes to lower load.
        assert by_key["AUTO-1"] == "alice"
        assert by_key["AUTO-2"] == "bob"
        assert by_key["AUTO-3"] in {"alice", "bob"}

    def test_assignments_empty_without_assignees(self, tmp_path) -> None:
        tickets = [ticket("AUTO-1", status="To Do", points=3)]
        plan = _planner(tmp_path, tickets, capacity=20).build_plan()
        assert plan.assignments == {}
        assert plan.selected[0].assignee is None


class TestPlannerStateIntegration:
    def test_components_fall_back_to_local_state(self, tmp_path) -> None:
        tickets = [ticket("AUTO-1", status="To Do", points=3)]
        intake_state = {
            "idem-1": {
                "jira_key": "AUTO-1",
                "summary": "First",
                "points": 3,
                "components": ["reports"],
                "depends_on": [],
            }
        }
        plan = _planner(tmp_path, tickets, capacity=20, intake_state=intake_state).build_plan()
        assert plan.selected[0].components == ["reports"]
