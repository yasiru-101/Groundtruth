"""STALE_IN_PROGRESS: ticket says work is happening; the branch says otherwise.

Fires when a ticket is In Progress with a linked branch whose newest commit
is older than the policy staleness window (or the branch has no commits at
all / is missing from the repo). In Progress tickets with NO linked branch
are skipped here — nothing is claiming progress — their status age is scored
by the staleness_health dimension instead.
"""

from __future__ import annotations

from datetime import timedelta

from groundtruth.clock import Clock
from groundtruth.contracts.board import BoardState, RepoState, is_in_progress
from groundtruth.contracts.discrepancy import (
    ActionVerb,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    ProposedAction,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.common import evidence
from groundtruth.scoring.policy import ScoringPolicy, load_policy


def detect_stale(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
) -> list[Discrepancy]:
    policy = policy or load_policy()
    as_of = clock.now()
    window = timedelta(days=policy.staleness_window_days)
    found: list[Discrepancy] = []

    for ticket in sorted(board.tickets, key=lambda t: t.key):
        if ticket.is_control or not is_in_progress(ticket):
            continue
        if not ticket.branch:
            continue

        branch = repo.branch(ticket.branch)
        tip = branch.tip if branch else None
        if tip is not None:
            age = as_of - tip.author_date
            if age <= window:
                continue

        proofs = [
            evidence(
                EvidenceKind.JIRA_CHANGELOG,
                ticket.key,
                board.jira_url(ticket.key),
                as_of,
                {
                    "status": ticket.status,
                    "status_changed_at": ticket.status_changed_at,
                },
            )
        ]
        if tip is not None:
            proofs.append(
                evidence(
                    EvidenceKind.COMMIT,
                    tip.sha,
                    repo.commit_url(tip.sha),
                    as_of,
                    {
                        "author_date": tip.author_date.isoformat(),
                        "subject": tip.subject,
                        "age_days": (as_of - tip.author_date).days,
                        "window_days": policy.staleness_window_days,
                        "branch": ticket.branch,
                    },
                )
            )
        else:
            proofs.append(
                evidence(
                    EvidenceKind.BRANCH,
                    ticket.branch,
                    repo.branch_url(ticket.branch),
                    as_of,
                    {
                        "found_in_repo": "no",
                        "window_days": policy.staleness_window_days,
                    },
                )
            )

        found.append(
            Discrepancy.build(
                type=DiscrepancyType.STALE_IN_PROGRESS,
                severity=DiscrepancySeverity.MEDIUM,
                subject=ticket.key,
                evidence=proofs,
                proposed_action=ProposedAction(
                    verb=ActionVerb.COMMENT,
                    target=ticket.key,
                    params={"reason": "no commit within the staleness window"},
                ),
                detected_at=as_of,
                as_of=as_of,
            )
        )
    return found
