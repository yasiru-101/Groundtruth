"""Intake Analyst: raw notes -> structured, idempotent, deduped Stories.

This is LLM hop (a). Everything after the LLM call is deterministic:
DoR gating, idempotency via Jira labels + local state, duplicate detection
against the existing board, and propose/apply through the changeset/ledger
system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from groundtruth.adapters.jira import JiraClient, adf_text
from groundtruth.adapters.llm import LLMClient, PromptName, _load_prompt
from groundtruth.agents.steward import BoardSteward
from groundtruth.clock import Clock, SystemClock
from groundtruth.config import RunMode, Settings
from groundtruth.contracts.board import BoardState, is_active
from groundtruth.contracts.discrepancy import (
    ActionVerb,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    ProposedAction,
)
from groundtruth.contracts.evidence import Evidence, EvidenceKind
from groundtruth.contracts.ledger import ApprovalRef, LedgerMode, LedgerOutcome
from groundtruth.contracts.story import (
    AcceptanceCriterion,
    DedupeVerdict,
    DefinitionOfReadyResult,
    DoRFailureCode,
    ProvenanceRef,
    Story,
    StoryStatus,
)
from groundtruth.detectors.common import evidence
from groundtruth.detectors.duplicate import jaccard, tokens
from groundtruth.ids import content_hash, idempotency_key
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.safety.approval import ChangeItem, ChangeSet, propose_changeset
from groundtruth.scoring.policy import ScoringPolicy, load_policy


class IntakeError(Exception):
    pass


_IDEM_BASE_LABEL = "gt-idem"
_IDEM_LABEL_PREFIX = "gt-idem-"
_POINTS_LABEL_PREFIX = "gt-points-"
_COMPONENT_LABEL_PREFIX = "gt-component-"
_ALLOWED_POINTS = frozenset({1, 2, 3, 5, 8})


@dataclass
class IntakeResult:
    """Outcome of a single decomposition + gating pass."""

    accepted: list[Story]
    refused: list[Story]
    duplicates: list[Discrepancy]
    rejected_raw: list[dict[str, Any]]


class IntakeAgent:
    def __init__(
        self,
        settings: Settings,
        jira: JiraClient,
        llm: LLMClient,
        steward: BoardSteward | None = None,
        ledger: LedgerWriter | None = None,
        clock: Clock | None = None,
        policy: ScoringPolicy | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._settings = settings
        self._jira = jira
        self._llm = llm
        self._steward = steward
        self._ledger = ledger
        self._clock = clock or SystemClock()
        self._policy = policy or load_policy()
        self._state_path = state_path or (settings.artifacts_dir / "intake_state.json")
        self._project_key = settings.jira_project_key

    # ------------------------------------------------------------------
    # Decomposition
    # ------------------------------------------------------------------

    def decompose(self, doc_path: Path, doc_id: str | None = None) -> IntakeResult:
        """Turn a raw notes file into gated Stories."""
        text = doc_path.read_text(encoding="utf-8")
        doc_id = doc_id or str(doc_path)
        variables = {"doc_id": doc_id, "text": text}

        raw_response = self._llm.complete(PromptName.INTAKE_DECOMPOSE, variables)
        llm_call_id = self._llm_call_id(variables)

        stories, rejected_raw = self._parse_response(
            raw_response, doc_id, text, llm_call_id
        )
        accepted, refused = self._apply_dor_gate(stories)
        duplicates = self._detect_duplicates(accepted, doc_id)
        return IntakeResult(accepted, refused, duplicates, rejected_raw)

    def _llm_call_id(self, variables: dict[str, Any]) -> str:
        """Deterministic identifier for this LLM invocation."""
        prompt_text = _load_prompt(PromptName.INTAKE_DECOMPOSE)
        return content_hash(
            PromptName.INTAKE_DECOMPOSE.value,
            self._settings.llm_model or "",
            json.dumps(variables, sort_keys=True, ensure_ascii=False),
            prompt_text,
        )

    def _parse_response(
        self,
        raw_response: str,
        doc_id: str,
        source_text: str,
        llm_call_id: str,
    ) -> tuple[list[Story], list[dict[str, Any]]]:
        text = raw_response.strip()
        # Strip optional markdown fences.
        if text.startswith("```"):
            parts = text.split("```", 2)
            text = parts[-1].strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise IntakeError(f"LLM response was not valid JSON: {exc}") from exc

        if isinstance(data, list):
            tickets_data = data
            rejected_raw: list[dict[str, Any]] = []
        elif isinstance(data, dict):
            tickets_data = data.get("tickets", [])
            rejected_raw = data.get("rejected", [])
        else:
            raise IntakeError(f"LLM response must be a JSON object or array, got {type(data).__name__}")

        stories: list[Story] = []
        for index, item in enumerate(tickets_data):
            story = self._item_to_story(item, doc_id, source_text, llm_call_id, index)
            stories.append(story)
        return stories, rejected_raw

    def _item_to_story(
        self,
        item: dict[str, Any],
        doc_id: str,
        source_text: str,
        llm_call_id: str,
        index: int,
    ) -> Story:
        summary = str(item.get("summary", "")).strip()
        description = str(item.get("description", "")).strip()

        criteria: list[AcceptanceCriterion] = []
        for n, ac in enumerate(item.get("acceptance_criteria", []), start=1):
            given = str(ac.get("given", "")).strip()
            when = str(ac.get("when", "")).strip()
            then = str(ac.get("then", "")).strip()
            raw = f"Given: {given} When: {when} Then: {then}".strip()
            criteria.append(
                AcceptanceCriterion(
                    ac_id=f"INTAKE-{index + 1}#{n}",
                    given=given,
                    when=when,
                    then=then,
                    raw=raw,
                    is_wellformed=bool(given and when and then),
                )
            )

        points_raw = item.get("points")
        try:
            points = int(points_raw) if points_raw is not None else None
        except (TypeError, ValueError):
            points = None

        components = [
            str(c).strip()
            for c in item.get("components", [])
            if str(c).strip()
        ]
        depends_on = [
            str(d).strip()
            for d in item.get("depends_on", [])
            if str(d).strip()
        ]

        span_start, span_end = self._find_span(source_text, summary)
        normalized_ac = self._normalize_ac_text(criteria)
        idem = idempotency_key(doc_id, normalized_ac)[:32]

        return Story(
            idempotency_key=idem,
            summary=summary,
            description=description,
            acceptance_criteria=criteria,
            points=points,
            components=components,
            depends_on=depends_on,
            status=StoryStatus.DRAFT,
            source=ProvenanceRef(
                doc_id=doc_id,
                char_span_start=span_start,
                char_span_end=span_end,
                llm_call_id=llm_call_id,
            ),
        )

    @staticmethod
    def _normalize_ac_text(criteria: list[AcceptanceCriterion]) -> str:
        parts = [ac.raw.lower().strip() for ac in criteria]
        return "\n".join(parts)

    @staticmethod
    def _find_span(source_text: str, summary: str) -> tuple[int, int]:
        if not summary:
            return 0, 0
        idx = source_text.find(summary)
        if idx == -1:
            idx = source_text.lower().find(summary.lower())
        if idx == -1:
            return 0, 0
        return idx, idx + len(summary)

    # ------------------------------------------------------------------
    # DoR gate
    # ------------------------------------------------------------------

    def _apply_dor_gate(self, stories: list[Story]) -> tuple[list[Story], list[Story]]:
        graph = self._dependency_graph(stories)
        cyclic_keys = self._cyclic_nodes(graph)

        accepted: list[Story] = []
        refused: list[Story] = []
        checked_at = self._clock.now()

        for story in stories:
            failures: list[str] = []
            if not story.acceptance_criteria:
                failures.append(DoRFailureCode.NO_AC.value)
            elif any(not ac.is_wellformed for ac in story.acceptance_criteria):
                failures.append(DoRFailureCode.AC_MALFORMED.value)
            if story.points is None or story.points not in _ALLOWED_POINTS:
                failures.append(DoRFailureCode.NO_POINTS.value)
            if not story.components:
                failures.append(DoRFailureCode.NO_COMPONENT.value)
            if story.idempotency_key in cyclic_keys:
                failures.append(DoRFailureCode.CIRCULAR_DEP.value)

            story.dor = DefinitionOfReadyResult(
                passed=not failures,
                failures=failures,
                checked_at=checked_at,
            )
            if failures:
                refused.append(story)
            else:
                accepted.append(story)

        return accepted, refused

    def _dependency_graph(self, stories: list[Story]) -> dict[str, list[str]]:
        summary_to_key = {
            s.summary.lower().strip(): s.idempotency_key for s in stories
        }
        graph: dict[str, list[str]] = {}
        for story in stories:
            deps: list[str] = []
            for dep in story.depends_on:
                target = summary_to_key.get(dep.lower().strip())
                if target:
                    deps.append(target)
            graph[story.idempotency_key] = deps
        return graph

    @staticmethod
    def _cyclic_nodes(graph: dict[str, list[str]]) -> set[str]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node: WHITE for node in graph}
        cyclic: set[str] = set()

        def dfs(node: str, stack: list[str]) -> None:
            color[node] = GRAY
            for neighbor in graph.get(node, []):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found a cycle; mark all nodes in the cycle.
                    try:
                        start = stack.index(neighbor)
                        cyclic.update(stack[start:])
                    except ValueError:
                        cyclic.add(neighbor)
                elif color[neighbor] == WHITE:
                    dfs(neighbor, stack + [neighbor])
            color[node] = BLACK

        for node in graph:
            if color[node] == WHITE:
                dfs(node, [node])
        return cyclic

    # ------------------------------------------------------------------
    # Dedupe
    # ------------------------------------------------------------------

    def _detect_duplicates(
        self, stories: list[Story], doc_id: str
    ) -> list[Discrepancy]:
        if self._steward is None:
            return []

        board, _ = self._steward.collect()
        as_of = self._clock.now()
        found: list[Discrepancy] = []

        for story in stories:
            best_key: str | None = None
            best_sim = 0.0
            story_tokens = tokens(story.summary, self._policy.token_min_length)
            for ticket in board.tickets:
                if not is_active(ticket):
                    continue
                if ticket.is_control:
                    continue
                ticket_tokens = tokens(ticket.summary, self._policy.token_min_length)
                sim = jaccard(story_tokens, ticket_tokens)
                if sim > best_sim:
                    best_sim = sim
                    best_key = ticket.key

            if best_key and best_sim >= self._policy.duplicate_threshold:
                story.dedupe = DedupeVerdict(
                    candidate_jira_keys=[best_key],
                    similarity=best_sim,
                    method="token-set jaccard (plural-folded)",
                    threshold=self._policy.duplicate_threshold,
                    human_confirmed=None,
                )
                found.append(
                    self._duplicate_discrepancy(
                        story, best_key, best_sim, board, doc_id, as_of
                    )
                )

        return found

    def _duplicate_discrepancy(
        self,
        story: Story,
        existing_key: str,
        similarity: float,
        board: BoardState,
        doc_id: str,
        as_of: datetime,
    ) -> Discrepancy:
        existing_url = board.jira_url(existing_key)
        new_url = Path(doc_id).as_uri() if Path(doc_id).exists() else doc_id
        return Discrepancy.build(
            type=DiscrepancyType.DUPLICATE_SUSPECTED,
            severity=DiscrepancySeverity.LOW,
            subject=f"{existing_key}+new:{story.idempotency_key}",
            evidence=[
                evidence(
                    EvidenceKind.JIRA_CHANGELOG,
                    existing_key,
                    existing_url,
                    as_of,
                    {
                        "summary": story.summary,
                        "similarity": f"{similarity:.3f}",
                        "threshold": str(self._policy.duplicate_threshold),
                        "method": "token-set jaccard (plural-folded)",
                    },
                ),
                evidence(
                    EvidenceKind.LEDGER,
                    story.idempotency_key,
                    new_url,
                    as_of,
                    {"source_doc": doc_id, "status": "intake_candidate"},
                ),
            ],
            proposed_action=ProposedAction(
                verb=ActionVerb.NONE,
                target=existing_key,
                params={
                    "note": "Suspected duplicate detected at intake; human confirmation required.",
                    "similarity": f"{similarity:.3f}",
                },
                requires_approval=True,
            ),
            detected_at=as_of,
            as_of=as_of,
        )

    # ------------------------------------------------------------------
    # Propose / apply
    # ------------------------------------------------------------------

    def propose(self, doc_path: Path, doc_id: str | None = None) -> ChangeSet:
        """Build a changeset of create_ticket actions for accepted stories."""
        result = self.decompose(doc_path, doc_id)
        items: list[ChangeItem] = []
        for story in result.accepted:
            items.append(
                ChangeItem(
                    action="intake.create_ticket",
                    subject=story.idempotency_key,
                    params={"story": story.model_dump(mode="json")},
                )
            )

        description = (
            f"Intake from {doc_path.name}: "
            f"{len(result.accepted)} create(s), "
            f"{len(result.refused)} refused, "
            f"{len(result.duplicates)} duplicate suspect(s), "
            f"{len(result.rejected_raw)} rejected raw item(s)"
        )
        return propose_changeset(
            self._settings.artifacts_dir, items, description=description
        )

    def apply(
        self,
        changeset: ChangeSet,
        approval: ApprovalRef,
        run_dir: Path | None = None,
    ) -> list[Story]:
        """Create Jira issues for the accepted stories in a changeset."""
        if not self._project_key:
            raise IntakeError("JIRA_PROJECT_KEY is required to apply intake")

        existing = self._existing_by_idem(self._project_key)
        local_state = self._load_state()
        created: list[Story] = []
        mode = self._ledger_mode()

        for item in changeset.items:
            if item.action != "intake.create_ticket":
                continue
            idem_key = item.subject
            existing_key = existing.get(idem_key) or local_state.get(idem_key, {}).get("jira_key")
            if existing_key:
                self._log_skip(idem_key, existing_key, approval, mode)
                continue

            story = Story.model_validate(item.params["story"])
            jira_key = self._create_jira_issue(story)
            self._finalize_story(story, jira_key)
            self._save_to_local_state(local_state, idem_key, story)
            self._log_create(story, approval, mode)
            created.append(story)

        self._resolve_dependencies(local_state, created)
        self._save_state(local_state)
        return created

    def _create_jira_issue(self, story: Story) -> str:
        fields: dict[str, Any] = {
            "project": {"key": self._project_key},
            "summary": story.summary,
            "description": adf_text(self._render_description(story)),
            "issuetype": {"name": "Story"},
            "labels": self._build_labels(story),
        }
        response = self._jira.create_issue(fields)
        key = response.get("key")
        if not key:
            raise IntakeError(f"Jira create_issue returned no key: {response}")

        comment = (
            f"Created by Groundtruth intake from "
            f"{story.source.doc_id if story.source else 'unknown'} "
            f"(idem: {story.idempotency_key})."
        )
        self._jira.add_comment(key, comment)
        return key

    @staticmethod
    def _render_description(story: Story) -> str:
        lines: list[str] = []
        if story.description:
            lines.append(story.description)
            lines.append("")
        for ac in story.acceptance_criteria:
            lines.append(f"Given: {ac.given}")
            lines.append(f"When: {ac.when}")
            lines.append(f"Then: {ac.then}")
            lines.append("")
        return "\n".join(lines).strip()

    @staticmethod
    def _build_labels(story: Story) -> list[str]:
        labels = [_IDEM_BASE_LABEL, f"{_IDEM_LABEL_PREFIX}{story.idempotency_key}"]
        if story.points is not None:
            labels.append(f"{_POINTS_LABEL_PREFIX}{story.points}")
        for component in story.components:
            labels.append(f"{_COMPONENT_LABEL_PREFIX}{component}")
        return labels

    def _finalize_story(self, story: Story, jira_key: str) -> None:
        story.jira_key = jira_key
        story.status = StoryStatus.READY
        for index, ac in enumerate(story.acceptance_criteria, start=1):
            ac.ac_id = f"{jira_key}#{index}"

    # ------------------------------------------------------------------
    # Local state + idempotency
    # ------------------------------------------------------------------

    def _existing_by_idem(self, project_key: str) -> dict[str, str]:
        """Map idempotency keys to Jira issue keys using gt-idem labels."""
        try:
            issues = self._jira.search(
                f'project = "{project_key}" AND labels = "{_IDEM_BASE_LABEL}"',
                fields=["key", "labels"],
            )
        except Exception:
            return {}

        result: dict[str, str] = {}
        for issue in issues:
            key = issue.get("key", "")
            for label in issue.get("fields", {}).get("labels", []):
                if label.startswith(_IDEM_LABEL_PREFIX) and label != _IDEM_BASE_LABEL:
                    idem_key = label[len(_IDEM_LABEL_PREFIX):]
                    result[idem_key] = key
        return result

    def _load_state(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {}
        return json.loads(self._state_path.read_text(encoding="utf-8"))

    def _save_state(self, state: dict[str, Any]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
            newline="\n",
        )

    def _save_to_local_state(
        self, state: dict[str, Any], idem_key: str, story: Story
    ) -> None:
        state[idem_key] = {
            "jira_key": story.jira_key,
            "summary": story.summary,
            "points": story.points,
            "components": story.components,
            "depends_on": [],
        }

    def _resolve_dependencies(
        self, state: dict[str, Any], created: list[Story]
    ) -> None:
        """Map depends_on summary strings to Jira keys using local state."""
        summary_to_key: dict[str, str] = {}
        key_to_idem: dict[str, str] = {}
        for idem_key, entry in state.items():
            summary = str(entry.get("summary", "")).strip().lower()
            jira_key = entry.get("jira_key")
            if summary and jira_key:
                summary_to_key[summary] = jira_key
                key_to_idem[jira_key] = idem_key
        for story in created:
            if story.jira_key:
                key_to_idem[story.jira_key] = story.idempotency_key
                summary_to_key[story.summary.strip().lower()] = story.jira_key

        for story in created:
            entry = state.get(story.idempotency_key)
            if entry is None:
                continue
            resolved: list[str] = []
            for dep in story.depends_on:
                dep_clean = dep.strip()
                dep_lower = dep_clean.lower()
                target = summary_to_key.get(dep_lower)
                if not target and dep_clean in key_to_idem:
                    target = dep_clean
                if target:
                    resolved.append(target)
            entry["depends_on"] = resolved

    # ------------------------------------------------------------------
    # Ledger
    # ------------------------------------------------------------------

    def _ledger_mode(self) -> LedgerMode:
        from groundtruth.adapters.base import Envelope

        # We do not store the envelope directly; infer from settings run_mode.
        if self._settings.run_mode == RunMode.REPLAY:
            return LedgerMode.REPLAY
        return LedgerMode.APPLY

    def _log_create(
        self, story: Story, approval: ApprovalRef, mode: LedgerMode
    ) -> None:
        if self._ledger is None:
            return
        self._ledger.append(
            actor="intake",
            action="intake.create_ticket",
            mode=mode,
            subject=story.jira_key or story.idempotency_key,
            inputs_hash=story.idempotency_key,
            outputs_hash=content_hash(story.model_dump_json()),
            evidence=[
                {
                    "kind": "jira_changelog",
                    "ref": story.jira_key or "",
                    "url": "",
                    "detail": {"source_doc": story.source.doc_id if story.source else ""},
                }
            ],
            approval=approval,
            outcome=LedgerOutcome.OK,
        )

    def _log_skip(
        self,
        idem_key: str,
        jira_key: str,
        approval: ApprovalRef,
        mode: LedgerMode,
    ) -> None:
        if self._ledger is None:
            return
        self._ledger.append(
            actor="intake",
            action="intake.create_ticket",
            mode=mode,
            subject=jira_key,
            inputs_hash=idem_key,
            outputs_hash=content_hash(jira_key),
            approval=approval,
            outcome=LedgerOutcome.OK,
            error="skipped: idempotency key already exists",
        )
