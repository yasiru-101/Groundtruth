"""Reporting agent: read-only sprint health, score delta, and standup prose."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from groundtruth.adapters.base import ReplayMiss
from groundtruth.adapters.llm import LLMClient, LLMError, PromptName
from groundtruth.agents.planner import PlannerAgent
from groundtruth.agents.steward import BoardSteward
from groundtruth.config import RunMode, Settings
from groundtruth.contracts.board import is_active
from groundtruth.contracts.discrepancy import Discrepancy, DiscrepancyType
from groundtruth.contracts.ledger import LedgerMode
from groundtruth.contracts.report import (
    ReportResult,
    ScoreDelta,
    SprintHealth,
    StandupItem,
)
from groundtruth.contracts.score import TruthfulnessScore
from groundtruth.ledger.reader import verify_chain
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.scoring import compute_control_score, compute_score


class ReportingError(Exception):
    pass


class ReportingAgent:
    def __init__(
        self,
        settings: Settings,
        steward: BoardSteward,
        llm: LLMClient | None = None,
        ledger: LedgerWriter | None = None,
    ) -> None:
        self._settings = settings
        self._steward = steward
        self._llm = llm
        self._ledger = ledger

    def report(self, run_dir: Path) -> ReportResult:
        run_dir.mkdir(parents=True, exist_ok=True)
        audit = self._steward.audit()
        ledger_entries = self._ledger_entries()
        score = compute_score(
            audit.board,
            audit.repo,
            audit.clock,
            audit.policy,
            ledger_entries=ledger_entries,
        )
        control_score = compute_control_score(
            audit.board,
            audit.repo,
            audit.clock,
            audit.policy,
            ledger_entries=ledger_entries,
        )
        plan = PlannerAgent(
            audit.board,
            audit.repo,
            audit.clock,
            intake_state_path=self._settings.artifacts_dir / "intake_state.json",
        ).build_plan()
        health = self._health(plan.velocity, plan.capacity, plan.over_committed, audit.discrepancies)
        items = self._items(audit.board.tickets, plan, audit.discrepancies)
        delta = self._score_delta(score)
        prose, prose_source = self._prose(health, items, delta)
        result = ReportResult(
            health=health,
            items=items,
            delta=delta,
            prose=prose,
            prose_source=prose_source,
        )

        payload = result.model_dump_json(indent=2)
        (run_dir / "report.json").write_text(payload + "\n", encoding="utf-8", newline="\n")
        (run_dir / "report.md").write_text(prose + "\n", encoding="utf-8", newline="\n")
        self._append_ledger(audit.board.project_key, score, control_score, result, payload)
        return result

    def _ledger_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for ledger_path in sorted(self._settings.artifacts_dir.glob("run_*/ledger.jsonl")):
            entries.extend(verify_chain(ledger_path))
        return entries

    @staticmethod
    def _health(
        velocity: int,
        capacity: int,
        over_committed: bool,
        discrepancies: list[Discrepancy],
    ) -> SprintHealth:
        unverified = {
            DiscrepancyType.UNVERIFIED_NO_MAPPING,
            DiscrepancyType.UNVERIFIED_MAPPING_STALE,
            DiscrepancyType.UNVERIFIED_TEST_FAILING,
        }
        return SprintHealth(
            velocity_forecast=velocity,
            capacity=capacity,
            over_committed=over_committed,
            open_discrepancies=len(discrepancies),
            unverified_count=sum(d.type in unverified for d in discrepancies),
            stale_count=sum(
                d.type is DiscrepancyType.STALE_IN_PROGRESS for d in discrepancies
            ),
        )

    @staticmethod
    def _items(tickets: list[Any], plan: Any, discrepancies: list[Discrepancy]) -> list[StandupItem]:
        planned = {
            ticket.key: ticket for ticket in [*plan.selected, *plan.unscheduled]
        }
        by_subject: dict[str, list[Discrepancy]] = {}
        for discrepancy in discrepancies:
            by_subject.setdefault(discrepancy.subject, []).append(discrepancy)

        items: list[StandupItem] = []
        for ticket in sorted(tickets, key=lambda item: item.key):
            if ticket.is_control or not is_active(ticket):
                continue
            planned_ticket = planned.get(ticket.key)
            ticket_discrepancies = by_subject.get(ticket.key, [])
            items.append(
                StandupItem(
                    jira_key=ticket.key,
                    summary=ticket.summary,
                    status=ticket.status,
                    assignee=(planned_ticket.assignee if planned_ticket else None),
                    blocked_by=(list(planned_ticket.depends_on) if planned_ticket else []),
                    discrepancy_count=len(ticket_discrepancies),
                    note="; ".join(
                        sorted(d.type.value for d in ticket_discrepancies)
                    ),
                )
            )
        return items

    def _score_delta(self, current: TruthfulnessScore) -> ScoreDelta | None:
        for path in reversed(sorted(self._settings.artifacts_dir.glob("run_*_score/score.json"))):
            prior = self._read_score(path)
            if prior is None or prior.get("policy_hash") != current.policy_hash:
                continue
            total = prior.get("total")
            if not isinstance(total, (int, float)):
                continue
            prior_dimensions = {
                item.get("name"): item.get("value")
                for item in prior.get("dimensions", [])
                if isinstance(item, dict)
                and isinstance(item.get("name"), str)
                and isinstance(item.get("value"), (int, float))
            }
            deltas = {
                dimension.name: float(dimension.value) - float(prior_value)
                for dimension in current.dimensions
                if dimension.value is not None
                and isinstance(prior_value := prior_dimensions.get(dimension.name), (int, float))
            }
            return ScoreDelta(
                previous_run_id=path.parent.name,
                policy_hash=current.policy_hash,
                comparable=True,
                dimension_deltas=deltas,
                overall_delta=current.total - float(total),
                reason=(
                    f"Compared with {path.parent.name}, the most recent score "
                    "using the current policy."
                ),
            )
        return None

    @staticmethod
    def _read_score(path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        score = payload.get("score") if isinstance(payload, dict) else None
        return score if isinstance(score, dict) else None

    def _prose(
        self,
        health: SprintHealth,
        items: list[StandupItem],
        delta: ScoreDelta | None,
    ) -> tuple[str, str]:
        payload = {
            "health": health.model_dump(mode="json"),
            "items": [item.model_dump(mode="json") for item in items],
            "delta": delta.model_dump(mode="json") if delta is not None else None,
        }
        if self._llm is not None:
            try:
                prose = self._llm.complete(PromptName.REPORT_PROSE, payload).strip()
                if self._valid_prose(prose):
                    return prose, "llm"
            except (LLMError, ReplayMiss):
                pass
        return self._template_prose(health, items, delta), "template"

    @staticmethod
    def _valid_prose(prose: str) -> bool:
        expected = ["## Standup", "## Sprint health", "## Score delta"]
        headings = [
            line.strip() for line in prose.splitlines() if line.strip().startswith("##")
        ]
        return bool(prose) and len(prose.split()) <= 400 and headings == expected

    @staticmethod
    def _template_prose(
        health: SprintHealth,
        items: list[StandupItem],
        delta: ScoreDelta | None,
    ) -> str:
        blocked = sum(bool(item.blocked_by) for item in items)
        risk = "The sprint is over-committed." if health.over_committed else "The sprint is within forecast capacity."
        delta_line = (
            "No comparable prior run."
            if delta is None
            else f"Score changed {delta.overall_delta:+.4f}. {delta.reason}"
        )
        return "\n".join(
            [
                "## Standup",
                f"{len(items)} active ticket(s) are in the current board snapshot.",
                f"{blocked} ticket(s) list local dependencies.",
                f"{health.open_discrepancies} discrepancy(s) need attention.",
                "",
                "## Sprint health",
                f"Velocity forecast is {health.velocity_forecast} points against {health.capacity} points of capacity.",
                risk,
                f"{health.open_discrepancies} open discrepancy(s), {health.unverified_count} unverified item(s), and {health.stale_count} stale item(s).",
                "",
                "## Score delta",
                delta_line,
            ]
        )

    def _append_ledger(
        self,
        project_key: str,
        score: TruthfulnessScore,
        control_score: TruthfulnessScore | None,
        result: ReportResult,
        payload: str,
    ) -> None:
        if self._ledger is None:
            return
        mode = (
            LedgerMode.REPLAY
            if self._settings.run_mode is RunMode.REPLAY
            else LedgerMode.DRY_RUN
        )
        self._ledger.append(
            actor="reporter",
            action="report.run",
            mode=mode,
            subject=project_key,
            inputs_hash=score.policy_hash,
            outputs_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            evidence=[
                {"score_total": score.total},
                {
                    "control_score_total": (
                        control_score.total if control_score is not None else None
                    )
                },
                {
                    "open_discrepancies": result.health.open_discrepancies,
                    "over_committed": result.health.over_committed,
                },
            ],
        )
