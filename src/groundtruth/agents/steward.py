"""Board Steward: read-only state assembly + the full detector sweep.

The steward is the only Phase 3 component that touches the outside
world: it pulls what Jira claims (``BoardState``) and what git/GitHub
can prove (``RepoState``) through the record/replay envelope, then
hands the pair plus a pinned clock to the pure detectors. Zero LLM
calls anywhere in this path — ``audit --run-mode replay`` reproduces
the same discrepancies from recorded fixtures, with ``as_of`` pinned to
the first replayed record so staleness math is deterministic.

Deleted tickets are not forgotten: any key the latest seed manifest
remembers but the board no longer shows becomes a GhostTicket and
travels with the board into scoring.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from groundtruth.adapters.base import Envelope
from groundtruth.adapters.gitlog import GitLog
from groundtruth.adapters.github import GitHubClient
from groundtruth.adapters.jira import JiraClient, adf_to_text
from groundtruth.clock import Clock, FrozenClock, SystemClock
from groundtruth.config import RunMode, Settings
from groundtruth.contracts.board import (
    BoardState,
    BoardTicket,
    GhostTicket,
    RepoBranch,
    RepoCheckRun,
    RepoCommit,
    RepoPullRequest,
    RepoState,
)
from groundtruth.contracts.discrepancy import Discrepancy
from groundtruth.contracts.ledger import LedgerMode
from groundtruth.detectors import (
    detect_duplicate,
    detect_mapping_stale,
    detect_merged_pr_ticket_open,
    detect_orphan_branch,
    detect_stale,
    detect_test_failing,
    detect_unverified_no_mapping,
)
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.scoring.ac_parser import parse_acceptance_criteria
from groundtruth.scoring.policy import ScoringPolicy, load_policy
from groundtruth.trace.manifest import latest_seed_manifest, latest_trace_manifest


class StewardError(Exception):
    pass


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            return None


def _points_from_labels(labels: list[str]) -> int | None:
    for label in labels:
        if label.startswith("gt-points-"):
            suffix = label[len("gt-points-"):]
            if suffix.isdigit():
                return int(suffix)
    return None


def _link_branches(tickets: list[BoardTicket], branch_names: list[str]) -> None:
    """Attach repo branches to tickets by key-in-path (feature/AUTO-1 -> AUTO-1)."""
    for branch in sorted(branch_names):
        segments = {segment.lower() for segment in branch.split("/")}
        for ticket in tickets:
            if ticket.branch is None and ticket.key.lower() in segments:
                ticket.branch = branch
                break


@dataclass
class _RawTicket:
    key: str
    summary: str
    description: str
    status: str
    labels: list[str]
    components: list[str]
    status_changed_at: datetime | None


@dataclass
class AuditResult:
    board: BoardState
    repo: RepoState
    discrepancies: list[Discrepancy]
    policy: ScoringPolicy
    clock: Clock


class BoardSteward:
    def __init__(
        self,
        *,
        settings: Settings,
        envelope: Envelope,
        jira: JiraClient,
        gitlog: GitLog,
        github: GitHubClient | None = None,
        project_key: str = "",
        control_label: str = "gt-control",
        base_branch: str = "main",
        policy: ScoringPolicy | None = None,
        ledger: LedgerWriter | None = None,
    ) -> None:
        self._settings = settings
        self._envelope = envelope
        self._jira = jira
        self._gitlog = gitlog
        self._github = github
        self._project_key = project_key or settings.jira_project_key
        self._control_label = control_label
        self._base_branch = base_branch
        self._policy = policy or load_policy()
        self._ledger = ledger

    # -- reads -------------------------------------------------------------

    def _read_tickets(self) -> list[_RawTicket]:
        jql = f'project = "{self._project_key}" ORDER BY key ASC'
        issues = self._jira.search(
            jql,
            fields=["summary", "status", "labels", "description", "components"],
        )
        raw: list[_RawTicket] = []
        for issue in sorted(issues, key=lambda i: i.get("key", "")):
            fields = issue.get("fields", {})
            description_doc = fields.get("description")
            key = issue.get("key", "")
            raw.append(
                _RawTicket(
                    key=key,
                    summary=fields.get("summary") or "",
                    description=adf_to_text(description_doc) if description_doc else "",
                    status=(fields.get("status") or {}).get("name") or "",
                    labels=list(fields.get("labels") or []),
                    components=[
                        component.get("name", "")
                        for component in (fields.get("components") or [])
                    ],
                    status_changed_at=self._last_status_change(key),
                )
            )
        return raw

    def _last_status_change(self, key: str) -> datetime | None:
        changed: datetime | None = None
        for entry in self._jira.get_changelog(key):
            items = entry.get("items") or []
            if any(item.get("field") == "status" for item in items):
                changed = _parse_dt(entry.get("created")) or changed
        return changed

    def _read_pull_requests(self) -> list[RepoPullRequest]:
        if self._github is None:
            return []
        entries = self._github.pr_list(state="all") or []
        pull_requests = [
            RepoPullRequest(
                number=int(entry.get("number", 0)),
                state=str(entry.get("state", "")),
                head_ref=entry.get("headRefName", ""),
                base_ref=entry.get("baseRefName", ""),
                merged_at=_parse_dt(entry.get("mergedAt")),
                merge_sha=(entry.get("mergeCommit") or {}).get("oid"),
                url=entry.get("url", ""),
            )
            for entry in entries
        ]
        pull_requests.sort(key=lambda pr: pr.number)
        return pull_requests

    def _read_check_runs(
        self, pull_requests: list[RepoPullRequest]
    ) -> list[RepoCheckRun]:
        if self._github is None:
            return []
        runs: list[RepoCheckRun] = []
        seen: set[str] = set()
        merged = [pr for pr in pull_requests if pr.is_merged and pr.merge_sha]
        for pr in sorted(merged, key=lambda p: p.number):
            if pr.merge_sha in seen:
                continue
            seen.add(pr.merge_sha)
            payload = self._github.check_runs(pr.merge_sha) or {}
            for run in payload.get("check_runs", []):
                if run.get("status") != "completed":
                    continue
                runs.append(
                    RepoCheckRun(
                        ref=pr.merge_sha,
                        name=run.get("name", ""),
                        conclusion=str(run.get("conclusion") or ""),
                    )
                )
        return runs

    def _pin_clock(self) -> Clock:
        hint = self._envelope.replay_clock_hint()
        if hint is not None:
            return FrozenClock(hint)
        return SystemClock()

    # -- assembly ----------------------------------------------------------

    def _collect(self) -> tuple[BoardState, RepoState, Clock]:
        if not self._project_key:
            raise StewardError(
                "BoardSteward needs a Jira project key "
                "(JIRA_PROJECT_KEY in .env or the scenario project_key)."
            )
        raw_tickets = self._read_tickets()
        branch_names = [
            name for name in self._gitlog.branches() if name != self._base_branch
        ]
        branch_commits = {
            name: self._gitlog.commits(name, base=self._base_branch)
            for name in sorted(branch_names)
        }
        pull_requests = self._read_pull_requests()
        check_runs = self._read_check_runs(pull_requests)

        clock = self._pin_clock()
        board = self._assemble_board(raw_tickets, branch_names, clock)
        repo = self._assemble_repo(branch_commits, pull_requests, check_runs)
        return board, repo, clock

    def _assemble_board(
        self,
        raw_tickets: list[_RawTicket],
        branch_names: list[str],
        clock: Clock,
    ) -> BoardState:
        tickets = [
            BoardTicket(
                key=raw.key,
                summary=raw.summary,
                description=raw.description,
                status=raw.status,
                labels=raw.labels,
                points=_points_from_labels(raw.labels),
                components=raw.components,
                is_control=self._control_label in raw.labels,
                status_changed_at=raw.status_changed_at,
                acceptance_criteria=parse_acceptance_criteria(raw.key, raw.description),
            )
            for raw in raw_tickets
        ]
        _link_branches(tickets, branch_names)

        trace_manifest = latest_trace_manifest(self._settings.artifacts_dir)
        trace = trace_manifest.snapshot() if trace_manifest else None

        return BoardState(
            project_key=self._project_key,
            tickets=tickets,
            ghosts=self._collect_ghosts({ticket.key for ticket in tickets}),
            trace=trace,
            as_of=clock.now(),
            jira_base_url=self._settings.jira_base_url,
        )

    def _collect_ghosts(self, live_keys: set[str]) -> list[GhostTicket]:
        manifest = latest_seed_manifest(self._settings.artifacts_dir)
        if manifest is None or manifest.project_key != self._project_key:
            return []
        return [
            GhostTicket(
                key=ticket.key,
                status=ticket.status,
                is_control=ticket.control,
            )
            for ticket in sorted(manifest.tickets, key=lambda t: t.key)
            if ticket.key not in live_keys
        ]

    def _assemble_repo(
        self,
        branch_commits: dict[str, list[dict[str, Any]]],
        pull_requests: list[RepoPullRequest],
        check_runs: list[RepoCheckRun],
    ) -> RepoState:
        branches = []
        for name, commits in sorted(branch_commits.items()):
            parsed: list[RepoCommit] = []
            for commit in commits:
                author_date = _parse_dt(commit.get("author_date"))
                if author_date is None:
                    raise StewardError(
                        f"Unparseable author date for commit {commit.get('sha')!r}"
                    )
                parsed.append(
                    RepoCommit(
                        sha=commit["sha"],
                        author_date=author_date,
                        subject=commit.get("subject", ""),
                        author_name=commit.get("author_name", ""),
                    )
                )
            branches.append(RepoBranch(name=name, commits=parsed))

        return RepoState(
            base_branch=self._base_branch,
            branches=branches,
            pull_requests=pull_requests,
            check_runs=check_runs,
            repo_url=self._repo_url(),
        )

    def _repo_url(self) -> str:
        if self._github is None:
            return ""
        return f"https://github.com/{self._github.slug}"

    # -- public API ----------------------------------------------------------

    def collect(self) -> tuple[BoardState, RepoState]:
        board, repo, _ = self._collect()
        return board, repo

    def audit(self) -> AuditResult:
        board, repo, clock = self._collect()
        discrepancies: list[Discrepancy] = []
        for detector in (
            detect_stale,
            detect_merged_pr_ticket_open,
            detect_orphan_branch,
            detect_unverified_no_mapping,
            detect_mapping_stale,
            detect_test_failing,
            detect_duplicate,
        ):
            discrepancies.extend(detector(board, repo, clock, policy=self._policy))
        discrepancies.sort(key=lambda d: (d.type.value, d.subject))
        self._ledger_append(board, discrepancies)
        return AuditResult(
            board=board,
            repo=repo,
            discrepancies=discrepancies,
            policy=self._policy,
            clock=clock,
        )

    def _ledger_append(
        self, board: BoardState, discrepancies: list[Discrepancy]
    ) -> None:
        if self._ledger is None:
            return
        joined = "|".join(sorted(d.discrepancy_id for d in discrepancies))
        self._ledger.append(
            actor="steward",
            action="audit.run",
            mode=(
                LedgerMode.REPLAY
                if self._envelope.mode is RunMode.REPLAY
                else LedgerMode.DRY_RUN
            ),
            subject=board.project_key,
            inputs_hash=self._policy.policy_hash,
            outputs_hash=hashlib.sha256(joined.encode("utf-8")).hexdigest(),
            evidence=[
                {
                    "type": d.type.value,
                    "subject": d.subject,
                    "discrepancy_id": d.discrepancy_id,
                }
                for d in discrepancies
            ],
        )
