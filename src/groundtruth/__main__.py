from __future__ import annotations

import io
import sys

import click

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from groundtruth.config import ExecMode, RunMode, Settings


@click.group()
@click.option(
    "--mode",
    type=click.Choice(["dry-run", "propose", "apply"], case_sensitive=False),
    default="dry-run",
    help="Execution mode. dry-run is default; apply requires --changeset.",
)
@click.option(
    "--run-mode",
    type=click.Choice(["live", "record", "replay"], case_sensitive=False),
    default="replay",
    help="Adapter I/O mode.",
)
@click.option(
    "--changeset",
    type=str,
    default=None,
    help="Changeset hash (required when --mode=apply).",
)
@click.pass_context
def cli(
    ctx: click.Context,
    mode: str,
    run_mode: str,
    changeset: str | None,
) -> None:
    """Groundtruth — keep a Jira board honest."""
    ctx.ensure_object(dict)
    ctx.obj["exec_mode"] = ExecMode(mode)
    ctx.obj["run_mode"] = RunMode(run_mode)
    ctx.obj["changeset"] = changeset

    if ctx.obj["exec_mode"] == ExecMode.APPLY and not changeset:
        raise click.UsageError("--mode=apply requires --changeset <hash>")


@cli.command()
@click.pass_context
def seed(ctx: click.Context) -> None:
    """Build the synthetic messy board + repo history."""
    click.echo("Phase 2: seed not yet implemented.")


@cli.command()
@click.pass_context
def reset(ctx: click.Context) -> None:
    """Tear down the synthetic board."""
    click.echo("Phase 2: reset not yet implemented.")


@cli.command()
@click.pass_context
def audit(ctx: click.Context) -> None:
    """Emit discrepancies with evidence."""
    click.echo("Phase 3: audit not yet implemented.")


@cli.command()
@click.pass_context
def score(ctx: click.Context) -> None:
    """Compute Board Truthfulness Score + evidence log."""
    click.echo("Phase 3: score not yet implemented.")


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def intake(ctx: click.Context, file: str) -> None:
    """Raw text → tickets (propose, then apply)."""
    click.echo(f"Phase 4: intake not yet implemented. File: {file}")


@cli.command()
@click.pass_context
def plan(ctx: click.Context) -> None:
    """Capacity-checked sprint proposal."""
    click.echo("Phase 4: plan not yet implemented.")


@cli.command()
@click.argument("key", type=str)
@click.pass_context
def deliver(ctx: click.Context, key: str) -> None:
    """Branch → red → green → PR."""
    click.echo(f"Phase 5: deliver not yet implemented. Key: {key}")


@cli.command()
@click.pass_context
def report(ctx: click.Context) -> None:
    """Standup digest, sprint health, score delta."""
    click.echo("Phase 5: report not yet implemented.")


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
