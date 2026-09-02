"""Sprint Planner: deterministic capacity/dependency proposal.

No LLM, no external writes. Velocity is computed from recently Done tickets;
selected tickets are topologically sorted by local-only dependencies, assigned
with load balancing, and flagged when demand exceeds capacity.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from groundtruth.clock import Clock
from groundtruth.contracts.board import BoardState, RepoState, is_active, is_done
from groundtruth.contracts.plan import PlannedTicket, SprintPlan


class PlannerError(Exception):
    pass


_DEFAULT_VELOCITY_WINDOW_DAYS = 30


@dataclass
class _Candidate:
    key: str
    summary: str
    points: int
    components: list[str]
    depends_on: list[str]
    assignee: str | None = None


class PlannerAgent:
    def __init__(
        self,
        board: BoardState,
        repo: RepoState,
        clock: Clock,
        *,
        capacity: int | None = None,
        velocity_window_days: int = _DEFAULT_VELOCITY_WINDOW_DAYS,
        assignees: list[str] | None = None,
        intake_state_path: Path | None = None,
    ) -> None:
        self._board = board
        self._repo = repo
        self._clock = clock
        self._capacity_override = capacity
        self._velocity_window_days = velocity_window_days
        self._assignees = assignees or []
        self._state_path = intake_state_path or (
            Path(board.jira_base_url).parent / "artifacts" / "intake_state.json"
            if board.jira_base_url
            else Path("artifacts/intake_state.json")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_plan(self) -> SprintPlan:
        candidates = self._candidates()
        dep_graph = self._dependency_graph(candidates)
        cycles = self._find_cycles(dep_graph)
        order = self._topological_order(candidates, dep_graph)
        capacity = self._capacity()

        selected: list[_Candidate] = []
        unscheduled: list[_Candidate] = []
        selected_keys: set[str] = set()
        total_selected = 0

        for ticket in order:
            deps_ok = all(dep in selected_keys for dep in ticket.depends_on)
            if not deps_ok:
                unscheduled.append(ticket)
                continue
            if total_selected + ticket.points <= capacity:
                selected.append(ticket)
                selected_keys.add(ticket.key)
                total_selected += ticket.points
            else:
                unscheduled.append(ticket)

        assigned, assignments = self._assign(selected)

        return SprintPlan(
            project_key=self._board.project_key,
            as_of=self._clock.now(),
            velocity=self._velocity(),
            capacity=capacity,
            total_candidate_points=sum(t.points for t in candidates),
            total_selected_points=total_selected,
            over_committed=sum(t.points for t in candidates) > capacity,
            cycles=cycles,
            selected=[self._to_planned(t) for t in assigned],
            unscheduled=[self._to_planned(t) for t in unscheduled],
            assignments=assignments,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _candidates(self) -> list[_Candidate]:
        state = self._load_intake_state()
        candidates: list[_Candidate] = []
        for ticket in self._board.tickets:
            if ticket.is_control:
                continue
            if not is_active(ticket):
                continue
            if ticket.points is None or ticket.points <= 0:
                continue
            meta = state.get(ticket.key, {})
            candidates.append(
                _Candidate(
                    key=ticket.key,
                    summary=ticket.summary,
                    points=ticket.points,
                    components=ticket.components or meta.get("components", []),
                    depends_on=meta.get("depends_on", []),
                    assignee=None,
                )
            )
        return sorted(candidates, key=lambda t: t.key)

    def _load_intake_state(self) -> dict[str, dict[str, Any]]:
        if self._state_path is None or not self._state_path.exists():
            return {}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for entry in data.values():
            key = entry.get("jira_key")
            if not key:
                continue
            result[key] = {
                "summary": entry.get("summary", ""),
                "points": entry.get("points"),
                "components": entry.get("components", []),
                "depends_on": [
                    d for d in entry.get("depends_on", []) if isinstance(d, str)
                ],
            }
        return result

    def _dependency_graph(self, candidates: list[_Candidate]) -> dict[str, list[str]]:
        keys = {c.key for c in candidates}
        return {c.key: [d for d in c.depends_on if d in keys] for c in candidates}

    def _find_cycles(self, graph: dict[str, list[str]]) -> list[list[str]]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {node: WHITE for node in graph}
        cycles: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()

        def dfs(node: str, stack: list[str]) -> None:
            color[node] = GRAY
            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    try:
                        start = stack.index(neighbor)
                        cycle = stack[start:]
                    except ValueError:
                        cycle = [neighbor, node]
                    key = tuple(sorted(cycle))
                    if key not in seen:
                        seen.add(key)
                        cycles.append(cycle)
                elif color[neighbor] == WHITE:
                    dfs(neighbor, stack + [neighbor])
            color[node] = BLACK

        for node in sorted(graph):
            if color[node] == WHITE:
                dfs(node, [node])
        return cycles

    def _topological_order(
        self,
        candidates: list[_Candidate],
        graph: dict[str, list[str]],
    ) -> list[_Candidate]:
        by_key = {c.key: c for c in candidates}
        # ``graph[key]`` lists prerequisites; a node's indegree is its
        # unresolved prerequisite count.
        indegree = {c.key: len(graph.get(c.key, [])) for c in candidates}

        # Tie-break: larger point value first, then key.
        queue = sorted(
            (k for k, v in indegree.items() if v == 0),
            key=lambda k: (-by_key[k].points, k),
        )
        ready = deque(queue)
        ordered: list[_Candidate] = []

        while ready:
            key = ready.popleft()
            ordered.append(by_key[key])
            for dep in sorted(graph.get(key, [])):
                indegree[dep] -= 1
                if indegree[dep] == 0:
                    ready.append(dep)
            ready = deque(sorted(ready, key=lambda k: (-by_key[k].points, k)))

        # Any remaining nodes are in cycles; append deterministically.
        remaining = sorted(
            (c for c in candidates if c.key not in {t.key for t in ordered}),
            key=lambda c: c.key,
        )
        ordered.extend(remaining)
        return ordered

    def _velocity(self) -> int:
        cutoff = self._clock.now() - timedelta(days=self._velocity_window_days)
        total = 0
        for ticket in self._board.tickets:
            if ticket.is_control:
                continue
            if not is_done(ticket):
                continue
            if ticket.points is None or ticket.points <= 0:
                continue
            if ticket.status_changed_at is None or ticket.status_changed_at < cutoff:
                continue
            total += ticket.points
        return total

    def _capacity(self) -> int:
        if self._capacity_override is not None:
            return max(0, self._capacity_override)
        return self._velocity()

    def _assign(
        self, selected: list[_Candidate]
    ) -> tuple[list[_Candidate], dict[str, list[str]]]:
        if not self._assignees:
            return selected, {}

        loads: dict[str, int] = {a: 0 for a in self._assignees}
        assignments: dict[str, list[str]] = {a: [] for a in self._assignees}
        result: list[_Candidate] = []

        for ticket in selected:
            assignee = min(loads, key=lambda a: loads[a])
            loads[assignee] += ticket.points
            assignments[assignee].append(ticket.key)
            result.append(
                _Candidate(
                    key=ticket.key,
                    summary=ticket.summary,
                    points=ticket.points,
                    components=ticket.components,
                    depends_on=ticket.depends_on,
                    assignee=assignee,
                )
            )
        return result, assignments

    @staticmethod
    def _to_planned(candidate: _Candidate) -> PlannedTicket:
        return PlannedTicket(
            key=candidate.key,
            summary=candidate.summary,
            points=candidate.points,
            components=candidate.components,
            depends_on=candidate.depends_on,
            assignee=candidate.assignee,
        )
