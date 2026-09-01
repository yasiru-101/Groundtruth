"""Aggregate the five dimensions into the TruthfulnessScore record.

The total is a weighted mean over measured dimensions only: a ``null``
dimension drops out of both the numerator and the weight denominator,
and the exclusion is printed by ``render_score`` — never silently
scored as 1.0. The control group is a second, full pass over tickets
the Delivery Agent never touches (``is_control``), so drift between the
two totals is board change, not delivery noise.
"""

from __future__ import annotations

import hashlib
import json

from groundtruth.clock import Clock
from groundtruth.contracts.board import BoardState, RepoState
from groundtruth.contracts.score import DimensionScore, TruthfulnessScore
from groundtruth.scoring.dimensions import (
    ac_validity,
    done_integrity,
    duplication_health,
    progress_integrity,
    staleness_health,
)
from groundtruth.scoring.policy import ScoringPolicy, load_policy

DIMENSION_ORDER = (
    "ac_validity",
    "progress_integrity",
    "done_integrity",
    "staleness_health",
    "duplication_health",
)

_UNITS = {
    "staleness_health": "ticket-days",
    "duplication_health": "tickets",
}


def board_snapshot_hash(board: BoardState, repo: RepoState) -> str:
    payload = {
        "board": board.model_dump(mode="json"),
        "repo": repo.model_dump(mode="json"),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def score_dimensions(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    ledger_entries: list[dict] | None = None,
    ledger_ref: str = "ledger",
    control: bool = False,
) -> list[DimensionScore]:
    policy = policy or load_policy()
    return [
        ac_validity(board, repo, clock, policy, control=control),
        progress_integrity(board, repo, clock, policy, control=control),
        done_integrity(board, repo, clock, policy, control=control),
        staleness_health(board, repo, clock, policy, control=control),
        duplication_health(
            board,
            repo,
            clock,
            policy,
            ledger_entries=ledger_entries,
            ledger_ref=ledger_ref,
            control=control,
        ),
    ]


def total_score(
    dimensions: list[DimensionScore], policy: ScoringPolicy
) -> float:
    numerator = 0.0
    weight_sum = 0.0
    for dim in dimensions:
        if dim.value is None:
            continue
        weight = policy.weight(dim.name)
        numerator += dim.value * weight
        weight_sum += weight
    if weight_sum == 0.0:
        return 0.0
    return numerator / weight_sum


def _build_score(
    dimensions: list[DimensionScore],
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy,
    control_group: float | None,
) -> TruthfulnessScore:
    return TruthfulnessScore(
        total=total_score(dimensions, policy),
        dimensions=dimensions,
        policy_version=policy.policy_version,
        policy_hash=policy.policy_hash,
        as_of=clock.now(),
        board_snapshot_hash=board_snapshot_hash(board, repo),
        control_group=control_group,
    )


def compute_score(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    ledger_entries: list[dict] | None = None,
    ledger_ref: str = "ledger",
) -> TruthfulnessScore:
    """Main score over non-control tickets, with the control-group total."""
    policy = policy or load_policy()
    dimensions = score_dimensions(
        board, repo, clock, policy,
        ledger_entries=ledger_entries, ledger_ref=ledger_ref, control=False,
    )
    control_dims = score_dimensions(
        board, repo, clock, policy,
        ledger_entries=ledger_entries, ledger_ref=ledger_ref, control=True,
    )
    control_group = (
        total_score(control_dims, policy)
        if any(d.value is not None for d in control_dims)
        else None
    )
    return _build_score(dimensions, board, repo, clock, policy, control_group)


def compute_control_score(
    board: BoardState,
    repo: RepoState,
    clock: Clock,
    policy: ScoringPolicy | None = None,
    *,
    ledger_entries: list[dict] | None = None,
    ledger_ref: str = "ledger",
) -> TruthfulnessScore | None:
    """Full dimension breakdown for the control group, or None if unmeasurable."""
    policy = policy or load_policy()
    dimensions = score_dimensions(
        board, repo, clock, policy,
        ledger_entries=ledger_entries, ledger_ref=ledger_ref, control=True,
    )
    if not any(d.value is not None for d in dimensions):
        return None
    return _build_score(dimensions, board, repo, clock, policy, None)


def render_score(score: TruthfulnessScore) -> str:
    lines = [
        f"Board Truthfulness Score: {score.total:.4f}",
        f"  policy {score.policy_version} (sha256 {score.policy_hash[:12]}...),"
        f" as_of {score.as_of.isoformat()}",
        f"  board snapshot {score.board_snapshot_hash[:12]}...",
    ]
    for dim in score.dimensions:
        if dim.value is None:
            lines.append(f"  {dim.name:<20} EXCLUDED ({dim.excluded_reason})")
            continue
        unit = _UNITS.get(dim.name, "")
        fraction = f"{dim.numerator}/{dim.denominator}"
        if unit:
            fraction = f"{fraction} {unit}"
        lines.append(
            f"  {dim.name:<20} {dim.value:.4f}  {fraction}  weight {dim.weight:.2f}"
        )
    if score.control_group is not None:
        lines.append(f"  control group: {score.control_group:.4f}")
    if score.evidence_log_path:
        lines.append(f"  evidence log: {score.evidence_log_path}")
    return "\n".join(lines)
