"""DUPLICATE_SUSPECTED: near-duplicate active tickets, proposal only.

Deterministic token-set Jaccard over ticket summaries — no model calls,
so the same board always yields the same suspects. Tokens are lowercased
alphanumeric runs; tokens shorter than policy.token_min_length and a
small stopword list are dropped; trailing plural 's' is folded
("timeouts" -> "timeout"). A suspected pair is PROPOSED, never
auto-resolved — closing a duplicate is a human decision.
"""

from __future__ import annotations

import re
from itertools import combinations

from groundtruth.clock import Clock
from groundtruth.contracts.board import BoardState, RepoState, is_active
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

_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({"the", "and", "for", "with", "from", "that", "this"})


def _fold_plural(word: str) -> str:
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokens(summary: str, min_length: int) -> set[str]:
    """Comparable token set for a summary (lowercase, plural-folded)."""
    return {
        _fold_plural(word)
        for word in _WORD.findall(summary.lower())
        if len(word) >= min_length and word not in _STOPWORDS
    }


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detect_duplicate(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
) -> list[Discrepancy]:
    if policy is None:
        policy = load_policy()
    as_of = clock.now()
    candidates = sorted(
        (t for t in board.tickets if is_active(t) and not t.is_control),
        key=lambda t: t.key,
    )

    found: list[Discrepancy] = []
    for first, second in combinations(candidates, 2):
        first_tokens = tokens(first.summary, policy.token_min_length)
        second_tokens = tokens(second.summary, policy.token_min_length)
        similarity = jaccard(first_tokens, second_tokens)
        if similarity < policy.duplicate_threshold:
            continue

        found.append(
            Discrepancy.build(
                type=DiscrepancyType.DUPLICATE_SUSPECTED,
                severity=DiscrepancySeverity.LOW,
                subject=f"{first.key}+{second.key}",
                evidence=[
                    evidence(
                        EvidenceKind.JIRA_CHANGELOG,
                        first.key,
                        board.jira_url(first.key),
                        as_of,
                        {
                            "summary": first.summary,
                            "status": first.status,
                            "tokens": " ".join(sorted(first_tokens)),
                            "method": "token-set jaccard (plural-folded)",
                            "similarity": f"{similarity:.3f}",
                            "threshold": str(policy.duplicate_threshold),
                        },
                    ),
                    evidence(
                        EvidenceKind.JIRA_CHANGELOG,
                        second.key,
                        board.jira_url(second.key),
                        as_of,
                        {
                            "summary": second.summary,
                            "status": second.status,
                            "tokens": " ".join(sorted(second_tokens)),
                        },
                    ),
                ],
                proposed_action=ProposedAction(
                    verb=ActionVerb.CLOSE_DUPLICATE,
                    target=second.key,
                    params={
                        "duplicate_of": first.key,
                        "similarity": f"{similarity:.3f}",
                    },
                    requires_approval=True,
                ),
                detected_at=as_of,
                as_of=as_of,
            )
        )
    return found
