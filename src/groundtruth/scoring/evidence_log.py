"""Itemised per-claim evidence log: every point in the score, one line, one artifact.

The log is the human-auditable half of the score: each dimension section
lists the population it measured, and each evidence line carries a
verdict, the artifact kind, a reference and a URL. Excluded dimensions
appear with their reason — reading the log you can always reconstruct
why the headline number is what it is.
"""

from __future__ import annotations

from pathlib import Path

from groundtruth.contracts.score import TruthfulnessScore
from groundtruth.scoring.score import _UNITS

LOG_NAME = "evidence_log.md"


def _dimension_header(dim) -> str:
    if dim.value is None:
        return f"## {dim.name} - EXCLUDED ({dim.excluded_reason})"
    unit = _UNITS.get(dim.name, "")
    fraction = f"{dim.numerator}/{dim.denominator}"
    if unit:
        fraction = f"{fraction} {unit}"
    contribution = dim.value * dim.weight
    return (
        f"## {dim.name} - {fraction}"
        f" (value {dim.value:.4f}, weight {dim.weight:.2f},"
        f" contributes {contribution:.4f})"
    )


def _evidence_lines(score: TruthfulnessScore) -> list[str]:
    lines: list[str] = []
    for dim in score.dimensions:
        lines.append(_dimension_header(dim))
        for item in dim.evidence:
            verdict = item.detail.get("verdict", "n/a")
            lines.append(
                f"- [{verdict}] {item.kind.value} {item.ref} {item.url}"
            )
            detail = "; ".join(
                f"{key}={item.detail[key]}" for key in sorted(item.detail)
            )
            if detail:
                lines.append(f"    {detail}")
        lines.append("")
    return lines


def render_evidence_log(
    score: TruthfulnessScore,
    control_score: TruthfulnessScore | None = None,
    *,
    run_id: str = "",
) -> str:
    lines = [
        "# Board Truthfulness Score - evidence log",
        "",
        f"- run: {run_id or 'n/a'}",
        f"- policy: {score.policy_version} (sha256 {score.policy_hash})",
        f"- as_of: {score.as_of.isoformat()}",
        f"- board snapshot: {score.board_snapshot_hash}",
        f"- total: {score.total:.4f}",
    ]
    if score.control_group is not None:
        lines.append(f"- control group: {score.control_group:.4f}")
    lines.append("")

    lines.append("# Main board")
    lines.append("")
    lines.extend(_evidence_lines(score))

    if control_score is not None:
        lines.append("# Control group (never touched by Delivery)")
        lines.append("")
        lines.append(f"total: {control_score.total:.4f}")
        lines.append("")
        lines.extend(_evidence_lines(control_score))

    return "\n".join(lines)


def write_evidence_log(
    run_dir: Path,
    score: TruthfulnessScore,
    control_score: TruthfulnessScore | None = None,
    *,
    run_id: str = "",
) -> Path:
    path = run_dir / LOG_NAME
    content = render_evidence_log(score, control_score, run_id=run_id)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")
    return path
