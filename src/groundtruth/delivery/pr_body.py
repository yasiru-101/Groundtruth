"""PR body renderer for Delivery Agent results."""

from __future__ import annotations

from groundtruth.contracts.delivery import DeliveryResult
from groundtruth.contracts.trace import TraceMatrixRow


def render(
    result: DeliveryResult,
    matrix_rows: list[TraceMatrixRow],
) -> str:
    """Render a markdown PR body from a delivery result and trace matrix."""
    lines: list[str] = []

    if not result.green:
        lines.append(
            ":warning: **DRAFT PR** — implementation did not reach a green gate.\n"
        )

    lines.append(f"## Summary")
    lines.append(f"Ticket: **{result.ticket_key}**")
    lines.append(f"Branch: `{result.branch}`")
    lines.append(f"Phase reached: `{result.phase.value}`")
    lines.append(f"Green gate: {'yes' if result.green else 'no'}")
    if result.head_sha:
        lines.append(f"Head SHA: `{result.head_sha}`")
    lines.append("")

    lines.append("## Traceability matrix")
    if matrix_rows:
        lines.append("| AC | Tests | Status |")
        lines.append("|---|---|---|")
        for row in matrix_rows:
            tests = ", ".join(f"`{n}`" for n in row.test_node_ids) or "—"
            lines.append(f"| {row.ac_id} | {tests} | {row.status.value} |")
    else:
        lines.append("_No acceptance criteria bindings were produced._")
    lines.append("")

    lines.append("## Red gate proof")
    if result.red_gate.classifications:
        lines.append("| Node | Failed | Kind | Excerpt |")
        lines.append("|---|---|---|---|")
        for c in result.red_gate.classifications:
            kind = c.failure_kind.value if c.failure_kind else "—"
            lines.append(
                f"| `{c.node_id}` | {c.failed} | {kind} | {c.message_excerpt} |"
            )
    else:
        lines.append("_No bound nodes to classify._")
    lines.append("")

    lines.append("## Repair log")
    if result.iterations:
        for it in result.iterations:
            lines.append(
                f"- Iteration {it.iteration} (`{it.phase}`): "
                f"green={it.green}, files={it.files_changed}, "
                f"violations={len(it.violations)}"
            )
            for note in it.notes:
                lines.append(f"  - {note}")
    else:
        lines.append("_No repair iterations were needed._")
    lines.append("")

    if result.refusals:
        lines.append("## Refusals")
        for refusal in result.refusals:
            lines.append(f"- {refusal}")
        lines.append("")

    if result.unrelated_failures:
        lines.append("## Unrelated failures")
        for node_id in result.unrelated_failures:
            lines.append(f"- `{node_id}`")
        lines.append("")

    lines.append("## Provenance")
    lines.append(f"- Run directory: `{result.run_dir}`")
    lines.append(f"- Draft: {result.draft}")
    if result.pr_url:
        lines.append(f"- PR URL: {result.pr_url}")
    if result.notes:
        for note in result.notes:
            lines.append(f"- {note}")

    return "\n".join(lines)
