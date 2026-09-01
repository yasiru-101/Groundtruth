"""The UNVERIFIED family: tickets that claim things their tests cannot prove.

Three rules, deliberately split (see the Phase 3 plan): seeded legacy tickets
have no AC->test binding because no Delivery Agent ever ran on them, so a
single detector would flag 100% of them — grading the seeder, not the board.
"""

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


def _tickets_with_acs(board: BoardState) -> list:
    return sorted(
        [t for t in board.tickets if t.acceptance_criteria and not t.is_control],
        key=lambda t: t.key,
    )


def detect_unverified_no_mapping(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy=None,
) -> list[Discrepancy]:
    """One aggregate discrepancy: coverage-of-mapping, a baseline — NOT a
    per-ticket defect. Fires only when some tickets have ACs to map."""
    as_of = clock.now()
    with_acs = _tickets_with_acs(board)
    if not with_acs:
        return []

    def is_bound(ticket) -> bool:
        trace = board.trace
        if trace is None:
            return False
        return any(l.ac_id.startswith(f"{ticket.key}#") for l in trace.bindings)

    unmapped = [t for t in with_acs if not is_bound(t)]
    if not unmapped:
        return []

    mapped = len(with_acs) - len(unmapped)
    return [
        Discrepancy.build(
            type=DiscrepancyType.UNVERIFIED_NO_MAPPING,
            severity=DiscrepancySeverity.LOW,
            subject=f"{board.project_key}:ac-mapping-coverage",
            evidence=[
                evidence(
                    EvidenceKind.JIRA_CHANGELOG,
                    t.key,
                    board.jira_url(t.key),
                    as_of,
                    {"acs": len(t.acceptance_criteria), "bound": "no"},
                )
                for t in unmapped
            ],
            proposed_action=ProposedAction(verb=ActionVerb.NONE),
            detected_at=as_of,
            as_of=as_of,
        ),
    ]


def detect_mapping_stale(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy=None,
) -> list[Discrepancy]:
    """A binding exists but its test is no longer collected."""
    trace = board.trace
    if trace is None:
        return []
    as_of = clock.now()
    collected = set(trace.collected_node_ids)
    found: list[Discrepancy] = []

    for link in sorted(trace.bindings, key=lambda l: (l.ac_id, l.test_node_id)):
        if link.test_node_id in collected:
            continue
        jira_key = link.ac_id.split("#", 1)[0]
        found.append(
            Discrepancy.build(
                type=DiscrepancyType.UNVERIFIED_MAPPING_STALE,
                severity=DiscrepancySeverity.MEDIUM,
                subject=link.ac_id,
                evidence=[
                    evidence(
                        EvidenceKind.TEST_RESULT,
                        link.test_node_id,
                        link.test_node_id,
                        as_of,
                        {
                            "collected": "no",
                            "bound_at": link.bound_at.isoformat(),
                        },
                    ),
                    evidence(
                        EvidenceKind.JIRA_CHANGELOG,
                        jira_key,
                        board.jira_url(jira_key),
                        as_of,
                        {"binding": link.ac_id},
                    ),
                ],
                proposed_action=ProposedAction(
                    verb=ActionVerb.COMMENT,
                    target=jira_key,
                    params={"reason": "bound test is no longer collected"},
                ),
                detected_at=as_of,
                as_of=as_of,
            )
        )
    return found


def detect_test_failing(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy=None,
) -> list[Discrepancy]:
    """A bound test is failing while the ticket claims Done."""
    trace = board.trace
    if trace is None:
        return []
    as_of = clock.now()
    failing = set(trace.failing_node_ids)
    found: list[Discrepancy] = []

    for ticket in sorted(board.tickets, key=lambda t: t.key):
        if ticket.is_control or not is_done(ticket):
            continue
        failing_links = [
            l for l in trace.bindings_for_ticket(ticket.key) if l.test_node_id in failing
        ]
        if not failing_links:
            continue

        proofs = [
            evidence(
                EvidenceKind.TEST_RESULT,
                link.test_node_id,
                link.test_node_id,
                as_of,
                {"outcome": "failed", "ac_id": link.ac_id},
            )
            for link in failing_links
        ]
        proofs.append(
            evidence(
                EvidenceKind.JIRA_CHANGELOG,
                ticket.key,
                board.jira_url(ticket.key),
                as_of,
                {"status": ticket.status},
            )
        )
        found.append(
            Discrepancy.build(
                type=DiscrepancyType.UNVERIFIED_TEST_FAILING,
                severity=DiscrepancySeverity.HIGH,
                subject=ticket.key,
                evidence=proofs,
                proposed_action=ProposedAction(
                    verb=ActionVerb.TRANSITION,
                    target=ticket.key,
                    params={"to": "In Progress"},
                ),
                detected_at=as_of,
                as_of=as_of,
            )
        )
    return found
