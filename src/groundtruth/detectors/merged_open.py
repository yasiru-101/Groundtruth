"""MERGED_PR_TICKET_OPEN: the PR says the work shipped; the board never noticed."""

from __future__ import annotations

from groundtruth.clock import Clock
from groundtruth.contracts.board import BoardState, RepoState, is_done
from groundtruth.contracts.discrepancy import (
    ActionVerb,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    ProposedAction,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.common import evidence


def detect_merged_pr_ticket_open(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy=None,
) -> list[Discrepancy]:
    as_of = clock.now()
    found: list[Discrepancy] = []

    for pr in sorted(repo.pull_requests, key=lambda p: p.number):
        if not pr.is_merged:
            continue
        ticket = board.ticket_for_branch(pr.head_ref)
        if ticket is None or ticket.is_control:
            continue
        if is_done(ticket):
            continue

        found.append(
            Discrepancy.build(
                type=DiscrepancyType.MERGED_PR_TICKET_OPEN,
                severity=DiscrepancySeverity.HIGH,
                subject=ticket.key,
                evidence=[
                    evidence(
                        EvidenceKind.PR,
                        str(pr.number),
                        pr.url,
                        as_of,
                        {
                            "merged_at": pr.merged_at.isoformat()
                            if pr.merged_at
                            else "",
                            "head": pr.head_ref,
                            "base": pr.base_ref,
                        },
                    ),
                    evidence(
                        EvidenceKind.JIRA_CHANGELOG,
                        ticket.key,
                        board.jira_url(ticket.key),
                        as_of,
                        {"status": ticket.status, "branch": pr.head_ref},
                    ),
                ],
                proposed_action=ProposedAction(
                    verb=ActionVerb.TRANSITION,
                    target=ticket.key,
                    params={"to": "Done"},
                ),
                detected_at=as_of,
                as_of=as_of,
            )
        )
    return found
