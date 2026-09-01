"""ORPHAN_BRANCH: real commits exist for work no ticket knows about."""

from __future__ import annotations

from groundtruth.clock import Clock
from groundtruth.contracts.board import BoardState, RepoState
from groundtruth.contracts.discrepancy import (
    ActionVerb,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
    ProposedAction,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.common import evidence


def detect_orphan_branch(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy=None,
) -> list[Discrepancy]:
    as_of = clock.now()
    found: list[Discrepancy] = []

    for branch in sorted(repo.branches, key=lambda b: b.name):
        if branch.name == repo.base_branch:
            continue
        if board.ticket_for_branch(branch.name) is not None:
            continue
        tip = branch.tip
        if tip is None:
            continue

        found.append(
            Discrepancy.build(
                type=DiscrepancyType.ORPHAN_BRANCH,
                severity=DiscrepancySeverity.LOW,
                subject=branch.name,
                evidence=[
                    evidence(
                        EvidenceKind.BRANCH,
                        branch.name,
                        repo.branch_url(branch.name),
                        as_of,
                        {"commits": len(branch.commits), "tip": tip.sha},
                    ),
                    evidence(
                        EvidenceKind.COMMIT,
                        tip.sha,
                        repo.commit_url(tip.sha),
                        as_of,
                        {
                            "author_date": tip.author_date.isoformat(),
                            "subject": tip.subject,
                        },
                    ),
                ],
                proposed_action=ProposedAction(
                    verb=ActionVerb.CREATE_TICKET,
                    target=branch.name,
                    params={"commits": str(len(branch.commits))},
                ),
                detected_at=as_of,
                as_of=as_of,
            )
        )
    return found
