"""The five truthfulness dimensions. Pure functions, zero I/O, zero LLM.

Each dimension renders as ``numerator/denominator`` (never a bare float)
over a defined population, and every numerator point cites an external
artifact through the same ``Evidence`` contract the detectors emit. A
dimension that cannot be measured returns ``value=None`` with
``excluded_reason`` set; the aggregate excludes it from the denominator
and the renderer prints the exclusion — a missing dimension is never
silently scored 1.0.

Populations (``control=False`` scores the main board; ``control=True``
scores the control group the Delivery Agent never touches):

- ``ac_validity``        every ticket (DoR is not status-bound)
- ``progress_integrity`` In Progress tickets + ghosts that claimed In Progress
- ``done_integrity``     Done/Resolved tickets
- ``staleness_health``   active tickets + non-terminal ghosts, in cap-weighted
                         ticket-days: numerator = sum(cap - min(days, cap)),
                         denominator = N * cap, so value == numerator/denominator
- ``duplication_health`` active tickets; confirmed pairs come from the ledger

Measurement stances that keep the score honest:

- A Done ticket needs BOTH a merged PR for its linked branch AND a
  completed successful check-run on that PR's merge SHA. Closing a
  ticket with no PR always costs more done_integrity (weight 0.35) than
  the staleness it hides (weight 0.15).
- Local pytest outcomes never enter done_integrity — only the GitHub CI
  conclusion on the merge SHA. An ``assert True`` suite cannot move it.
- A deleted ticket becomes a ghost: it re-enters the staleness budget at
  full penalty (and progress_integrity if it claimed In Progress), so
  deleting a stale ticket raises the score strictly less than fixing it.
- Freshness that cannot be proven is maximal staleness: a live ticket
  with no status-change timestamp scores the full cap, because the
  witness (Jira changelog) is missing, not because the ticket is new.

A pair counts as a human-confirmed duplicate only when the ledger holds
an entry with action ``duplicate.confirm``, outcome ``ok``, a non-null
``approval`` and subject ``KEYA+KEYB`` (the DUPLICATE_SUSPECTED subject
shape). Phase 5's confirmation flow must write exactly that entry.
Until a human confirms, duplication_health stays at 1.0 — a model's
judgment cannot move the headline number. A confirmed pair still counts
when one half was later deleted; deletion must not erase a confirmation.
"""

from __future__ import annotations

from datetime import timedelta

from groundtruth.clock import Clock
from groundtruth.contracts.board import (
    TERMINAL_DISPOSITION_STATUSES,
    BoardState,
    BoardTicket,
    GhostTicket,
    RepoState,
    is_active,
    is_done,
    is_in_progress,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.contracts.score import DimensionScore
from groundtruth.detectors.common import evidence
from groundtruth.scoring.policy import ScoringPolicy, load_policy

DUPLICATE_CONFIRM_ACTION = "duplicate.confirm"


def _population(board: BoardState, control: bool) -> list[BoardTicket]:
    return sorted(
        (t for t in board.tickets if t.is_control == control), key=lambda t: t.key
    )


def _ghosts(board: BoardState, control: bool) -> list[GhostTicket]:
    return sorted(
        (g for g in board.ghosts if g.is_control == control), key=lambda g: g.key
    )


def _excluded(name: str, policy: ScoringPolicy, reason: str) -> DimensionScore:
    return DimensionScore(
        name=name,
        value=None,
        numerator=0,
        denominator=0,
        weight=policy.weight(name),
        excluded_reason=reason,
    )


def _dimension(
    name: str,
    policy: ScoringPolicy,
    numerator: int,
    denominator: int,
    proofs: list,
) -> DimensionScore:
    return DimensionScore(
        name=name,
        value=numerator / denominator,
        numerator=numerator,
        denominator=denominator,
        weight=policy.weight(name),
        evidence=proofs,
    )


def ac_validity(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    control: bool = False,
) -> DimensionScore:
    policy = policy or load_policy()
    as_of = clock.now()
    tickets = _population(board, control)
    if not tickets:
        return _excluded(
            "ac_validity", policy, f"no {'control ' if control else ''}tickets on the board"
        )

    proofs = []
    passed = 0
    for ticket in tickets:
        acs = ticket.acceptance_criteria
        wellformed = sum(1 for ac in acs if ac.is_wellformed)
        ok = bool(acs) and wellformed == len(acs)
        if ok:
            passed += 1
        proofs.append(
            evidence(
                EvidenceKind.JIRA_CHANGELOG,
                ticket.key,
                board.jira_url(ticket.key),
                as_of,
                {
                    "verdict": "pass" if ok else "fail",
                    "summary": ticket.summary,
                    "ac_total": len(acs),
                    "ac_wellformed": wellformed,
                },
            )
        )
    return _dimension("ac_validity", policy, passed, len(tickets), proofs)


def progress_integrity(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    control: bool = False,
) -> DimensionScore:
    policy = policy or load_policy()
    as_of = clock.now()
    window = timedelta(days=policy.staleness_window_days)
    tickets = [t for t in _population(board, control) if is_in_progress(t)]
    ghosts = [
        g for g in _ghosts(board, control) if g.status.strip().lower() == "in progress"
    ]
    total = len(tickets) + len(ghosts)
    if total == 0:
        return _excluded("progress_integrity", policy, "no In Progress tickets")

    proofs = []
    passed = 0
    for ticket in tickets:
        branch = repo.branch(ticket.branch) if ticket.branch else None
        in_window = branch is not None and any(
            as_of - commit.author_date <= window for commit in branch.commits
        )
        if in_window:
            passed += 1
            commit = next(
                c for c in branch.commits if as_of - c.author_date <= window
            )
            proofs.append(
                evidence(
                    EvidenceKind.COMMIT,
                    commit.sha,
                    repo.commit_url(commit.sha),
                    as_of,
                    {
                        "verdict": "pass",
                        "ticket": ticket.key,
                        "branch": branch.name,
                        "author_date": commit.author_date.isoformat(),
                    },
                )
            )
            continue

        detail = {
            "verdict": "fail",
            "status": ticket.status,
            "status_changed_at": ticket.status_changed_at,
            "linked_branch": ticket.branch or "none",
        }
        if branch is not None and branch.commits:
            tip = branch.tip
            proofs.append(
                evidence(
                    EvidenceKind.COMMIT,
                    tip.sha,
                    repo.commit_url(tip.sha),
                    as_of,
                    {
                        **detail,
                        "author_date": tip.author_date.isoformat(),
                        "age_days": (as_of - tip.author_date).days,
                        "window_days": policy.staleness_window_days,
                    },
                )
            )
        else:
            proofs.append(
                evidence(
                    EvidenceKind.JIRA_CHANGELOG,
                    ticket.key,
                    board.jira_url(ticket.key),
                    as_of,
                    detail,
                )
            )

    for ghost in ghosts:
        proofs.append(
            evidence(
                EvidenceKind.JIRA_CHANGELOG,
                ghost.key,
                board.jira_url(ghost.key),
                as_of,
                {
                    "verdict": "fail",
                    "present_in": "seed manifest",
                    "status_at_deletion": ghost.status,
                    "reason": "deleted ticket cannot show commits",
                },
            )
        )
    return _dimension("progress_integrity", policy, passed, total, proofs)


def done_integrity(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    control: bool = False,
) -> DimensionScore:
    policy = policy or load_policy()
    as_of = clock.now()
    tickets = [t for t in _population(board, control) if is_done(t)]
    if not tickets:
        return _excluded("done_integrity", policy, "no Done tickets")

    proofs = []
    passed = 0
    for ticket in tickets:
        pr = repo.merged_pr_for_head(ticket.branch) if ticket.branch else None
        runs = repo.check_runs_for(pr.merge_sha) if (pr and pr.merge_sha) else []
        green = [r for r in runs if r.passed]
        ok = pr is not None and pr.merge_sha is not None and bool(green)
        if ok:
            passed += 1

        if pr is None:
            proofs.append(
                evidence(
                    EvidenceKind.JIRA_CHANGELOG,
                    ticket.key,
                    board.jira_url(ticket.key),
                    as_of,
                    {
                        "verdict": "fail",
                        "status": ticket.status,
                        "status_changed_at": ticket.status_changed_at,
                        "linked_branch": ticket.branch or "none",
                        "merged_pr": "none",
                    },
                )
            )
            continue

        proofs.append(
            evidence(
                EvidenceKind.PR,
                str(pr.number),
                pr.url,
                as_of,
                {
                    "verdict": "pass" if ok else "fail",
                    "ticket": ticket.key,
                    "head_ref": pr.head_ref,
                    "merged_at": pr.merged_at,
                    "merge_sha": pr.merge_sha or "none",
                },
            )
        )
        if not pr.merge_sha:
            continue
        if green:
            run = green[0]
            conclusion_detail = {
                "verdict": "pass",
                "check": run.name,
                "conclusion": run.conclusion,
            }
        elif runs:
            run = runs[0]
            conclusion_detail = {
                "verdict": "fail",
                "check": run.name,
                "conclusion": run.conclusion,
            }
        else:
            conclusion_detail = {
                "verdict": "fail",
                "check": "none",
                "conclusion": "no completed check runs on the merge SHA",
            }
        proofs.append(
            evidence(
                EvidenceKind.CHECK_RUN,
                pr.merge_sha,
                repo.commit_url(pr.merge_sha),
                as_of,
                conclusion_detail,
            )
        )
    return _dimension("done_integrity", policy, passed, len(tickets), proofs)


def staleness_health(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    control: bool = False,
) -> DimensionScore:
    policy = policy or load_policy()
    as_of = clock.now()
    cap = policy.stale_day_cap
    tickets = [t for t in _population(board, control) if is_active(t)]
    ghosts = [
        g
        for g in _ghosts(board, control)
        if g.status.strip().lower() not in TERMINAL_DISPOSITION_STATUSES
    ]
    total = len(tickets) + len(ghosts)
    if total == 0:
        return _excluded("staleness_health", policy, "no active tickets")

    proofs = []
    healthy_days = 0
    for ticket in tickets:
        if ticket.status_changed_at is None:
            days = cap
        else:
            days = max(0, min((as_of - ticket.status_changed_at).days, cap))
        healthy_days += cap - days
        proofs.append(
            evidence(
                EvidenceKind.JIRA_CHANGELOG,
                ticket.key,
                board.jira_url(ticket.key),
                as_of,
                {
                    "verdict": "pass" if days <= policy.staleness_window_days else "fail",
                    "status": ticket.status,
                    "status_changed_at": ticket.status_changed_at,
                    "stale_days": days,
                    "stale_day_cap": cap,
                },
            )
        )
    for ghost in ghosts:
        proofs.append(
            evidence(
                EvidenceKind.JIRA_CHANGELOG,
                ghost.key,
                board.jira_url(ghost.key),
                as_of,
                {
                    "verdict": "fail",
                    "present_in": "seed manifest",
                    "status_at_deletion": ghost.status or "unknown",
                    "stale_days": cap,
                    "stale_day_cap": cap,
                    "reason": "deleted tickets stale at full penalty",
                },
            )
        )
    denominator = total * cap
    return _dimension(
        "staleness_health", policy, healthy_days, denominator, proofs
    )


def confirmed_duplicate_pairs(entries: list[dict] | None) -> list[tuple[str, str]]:
    """Extract human-confirmed duplicate pairs from raw ledger entries.

    An entry confirms a pair when its action is ``duplicate.confirm``,
    its outcome is ``ok``, it carries an approval ref, and its subject is
    ``KEYA+KEYB`` — the same subject shape DUPLICATE_SUSPECTED emits.
    """
    pairs: set[tuple[str, str]] = set()
    for entry in entries or []:
        if entry.get("action") != DUPLICATE_CONFIRM_ACTION:
            continue
        if entry.get("outcome") != "ok" or not entry.get("approval"):
            continue
        parts = [p.strip() for p in str(entry.get("subject", "")).split("+")]
        if len(parts) == 2 and all(parts):
            pairs.add((min(parts), max(parts)))
    return sorted(pairs)


def duplication_health(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    ledger_entries: list[dict] | None = None,
    ledger_ref: str = "ledger",
    control: bool = False,
) -> DimensionScore:
    policy = policy or load_policy()
    as_of = clock.now()
    tickets = [t for t in _population(board, control) if is_active(t)]
    if not tickets:
        return _excluded("duplication_health", policy, "no active tickets")

    active_keys = {t.key for t in tickets}
    pairs = [
        pair
        for pair in confirmed_duplicate_pairs(ledger_entries)
        if pair[0] in active_keys or pair[1] in active_keys
    ]

    proofs = []
    if pairs:
        for first, second in pairs:
            proofs.append(
                evidence(
                    EvidenceKind.LEDGER,
                    f"{first}+{second}",
                    ledger_ref,
                    as_of,
                    {
                        "verdict": "fail",
                        "confirmed_pair": f"{first}+{second}",
                        "note": "human-confirmed duplicate in the ledger",
                    },
                )
            )
    else:
        proofs.append(
            evidence(
                EvidenceKind.LEDGER,
                "confirmed-duplicates",
                ledger_ref,
                as_of,
                {
                    "verdict": "pass",
                    "confirmed_pairs": "0",
                    "active_tickets": str(len(tickets)),
                    "note": "no human-confirmed duplicates in the ledger",
                },
            )
        )

    numerator = max(0, len(tickets) - len(pairs))
    return _dimension(
        "duplication_health", policy, numerator, len(tickets), proofs
    )
