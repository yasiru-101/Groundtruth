"""Shared in-memory builders for the Phase 3 detector + scoring tests.

Every fixture is a pure ``BoardState``/``RepoState`` value over a
``FrozenClock`` pinned at ``AS_OF``, so all age math (staleness window,
stale-day cap) is deterministic. The detectors under test never do I/O,
so these builders are the entire test harness.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from groundtruth.clock import FrozenClock
from groundtruth.contracts.board import (
    BoardState,
    BoardTicket,
    GhostTicket,
    RepoBranch,
    RepoCheckRun,
    RepoCommit,
    RepoPullRequest,
    RepoState,
    TraceSnapshot,
)
from groundtruth.contracts.story import AcceptanceCriterion
from groundtruth.contracts.trace import TraceLink

AS_OF = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def frozen_clock() -> FrozenClock:
    return FrozenClock(AS_OF)


def days_ago(days: float) -> datetime:
    return AS_OF - timedelta(days=days)


def ac(ac_id: str, *, wellformed: bool = True) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        ac_id=ac_id,
        given="given a board" if wellformed else "",
        when="when the steward audits" if wellformed else "",
        then="then evidence exists" if wellformed else "",
        raw=f"{ac_id} raw text",
        is_wellformed=wellformed,
    )


def ticket(key: str, **overrides) -> BoardTicket:
    fields = dict(
        key=key,
        summary=f"Work for {key}",
        status="To Do",
        branch=None,
        status_changed_at=days_ago(1),
        acceptance_criteria=[],
    )
    fields.update(overrides)
    return BoardTicket(**fields)


def ghost(key: str, **overrides) -> GhostTicket:
    fields = dict(key=key, status="In Progress")
    fields.update(overrides)
    return GhostTicket(**fields)


def commit(sha: str, age_days: float, subject: str = "do the work") -> RepoCommit:
    return RepoCommit(
        sha=sha,
        author_date=days_ago(age_days),
        subject=subject,
        author_name="Seed Bot",
    )


def branch(name: str, commits: list[RepoCommit] | None = None) -> RepoBranch:
    return RepoBranch(name=name, commits=commits or [])


def merged_pr(
    number: int,
    head: str,
    *,
    base: str = "main",
    age_days: float = 1.0,
    merge_sha: str | None = None,
    url: str = "",
) -> RepoPullRequest:
    return RepoPullRequest(
        number=number,
        state="MERGED",
        head_ref=head,
        base_ref=base,
        merged_at=days_ago(age_days),
        merge_sha=merge_sha or f"{number:04d}" + "0" * 36,
        url=url or f"https://github.com/acme/repo/pull/{number}",
    )


def check_run(ref: str, name: str = "ci", conclusion: str = "success") -> RepoCheckRun:
    return RepoCheckRun(ref=ref, name=name, conclusion=conclusion)


def board(
    tickets=(),
    ghosts=(),
    *,
    project_key: str = "AUTO",
    trace: TraceSnapshot | None = None,
) -> BoardState:
    return BoardState(
        project_key=project_key,
        tickets=list(tickets),
        ghosts=list(ghosts),
        trace=trace,
        as_of=AS_OF,
    )


def repo(
    branches=(),
    pull_requests=(),
    check_runs=(),
    *,
    base_branch: str = "main",
) -> RepoState:
    return RepoState(
        base_branch=base_branch,
        branches=list(branches),
        pull_requests=list(pull_requests),
        check_runs=list(check_runs),
    )


def trace_link(ac_id: str, node_id: str, *, bound_days_ago: float = 1.0) -> TraceLink:
    return TraceLink(
        ac_id=ac_id,
        test_node_id=node_id,
        bound_by="manifest",
        bound_at=days_ago(bound_days_ago),
        test_file_hash="0" * 64,
    )


def trace(bindings=(), collected=(), failing=()) -> TraceSnapshot:
    return TraceSnapshot(
        bindings=list(bindings),
        collected_node_ids=list(collected),
        failing_node_ids=list(failing),
        ran_at=AS_OF,
    )
