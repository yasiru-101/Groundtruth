from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from groundtruth.adapters.base import Envelope, FixtureCorrupt, FixtureStore, ReplayMiss
from groundtruth.adapters.github import GitHubClient, GitHubError
from groundtruth.adapters.gitlog import GitLog, GitLogError
from groundtruth.adapters.jira import JiraClient, JiraError
from groundtruth.adapters.llm import LLMClient
from groundtruth.agents import (
    AuditResult,
    BoardSteward,
    IntakeAgent,
    IntakeError,
    PlannerAgent,
    PlannerError,
    StewardError,
)
from groundtruth.clock import FrozenClock
from groundtruth.config import ExecMode, RunMode, Settings
from groundtruth.contracts.ledger import ApprovalRef, LedgerMode
from groundtruth.ledger.reader import ChainVerificationError, verify_chain
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.safety.approval import ChangeItem, load_changeset, propose_changeset
from groundtruth.safety.git_guard import GitGuard
from groundtruth.safety.workspace import SANDBOX_SENTINEL
from groundtruth.scoring import (
    board_snapshot_hash,
    compute_control_score,
    compute_score,
    render_score,
    write_evidence_log,
)
from groundtruth.scoring.policy import PolicyError, load_policy
from groundtruth.seed import (
    GitSeeder,
    JiraSeeder,
    Resetter,
    SeedError,
    build_manifest,
    load_scenario,
    validate_against_settings,
)


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


# -- seed/reset plumbing -------------------------------------------------------


def exec_options(f):
    """Shared exec options, also accepted after the subcommand."""
    f = click.option(
        "--mode",
        type=click.Choice(["dry-run", "propose", "apply"], case_sensitive=False),
        default=None,
        help="Execution mode. Overrides the group-level --mode.",
    )(f)
    f = click.option(
        "--run-mode",
        type=click.Choice(["live", "record", "replay"], case_sensitive=False),
        default=None,
        help="Adapter I/O mode. Overrides the group-level --run-mode.",
    )(f)
    f = click.option(
        "--changeset",
        type=str,
        default=None,
        help="Changeset hash (required when --mode=apply).",
    )(f)
    return f


def _merge_exec_options(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
) -> None:
    if mode is not None:
        ctx.obj["exec_mode"] = ExecMode(mode)
    if run_mode is not None:
        ctx.obj["run_mode"] = RunMode(run_mode)
    if changeset is not None:
        ctx.obj["changeset"] = changeset
    if ctx.obj["exec_mode"] == ExecMode.APPLY and not ctx.obj["changeset"]:
        raise click.UsageError("--mode=apply requires --changeset <hash>")


def _require_live(ctx: click.Context, command: str) -> None:
    if ctx.obj["run_mode"] != RunMode.LIVE:
        raise click.UsageError(
            f"{command} requires --run-mode live: it must create or destroy "
            "real state and cannot be served from recorded fixtures."
        )


def _workspace_identity(sandbox: Path) -> str:
    sentinel = sandbox / SANDBOX_SENTINEL
    if sentinel.exists():
        stored = sentinel.read_text(encoding="utf-8").strip()
        if stored:
            return stored
    return str(uuid.uuid4())


def _seed_stack(
    settings: Settings,
) -> tuple[GitGuard, JiraClient, GitHubClient | None]:
    sandbox = settings.workspace_dir
    workspace_id = _workspace_identity(sandbox)
    slug = ""
    if settings.github_repo_owner and settings.github_repo_name:
        slug = f"{settings.github_repo_owner}/{settings.github_repo_name}"
    guard = GitGuard(sandbox, workspace_id, allowed_remote=slug)
    envelope = Envelope(mode=RunMode.LIVE, store=FixtureStore(settings.fixtures_dir))
    jira_client = JiraClient(settings, envelope)
    github = GitHubClient(settings, envelope, guard) if slug else None
    return guard, jira_client, github


def _new_run_dir(settings: Settings, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = settings.artifacts_dir / f"run_{stamp}_{label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _approval_ref(changeset_hash: str) -> ApprovalRef:
    approved_by = os.getenv("GT_APPROVED_BY") or f"operator:{os.getenv('USERNAME', 'unknown')}"
    return ApprovalRef(
        changeset_hash=changeset_hash,
        approved_by=approved_by,
        approved_at=datetime.now(timezone.utc),
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


@cli.command()
@exec_options
@click.pass_context
def seed(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
) -> None:
    """Build the synthetic messy board + repo history."""
    _merge_exec_options(ctx, mode, run_mode, changeset)
    try:
        _require_live(ctx, "seed")
        _run_seed(ctx)
    except (SeedError, JiraError, GitHubError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


def _run_seed(ctx: click.Context) -> None:
    settings = Settings.from_env()
    scenario = load_scenario()
    validate_against_settings(settings, scenario)
    guard, jira_client, github = _seed_stack(settings)
    exec_mode = ctx.obj["exec_mode"]

    jira_seeder = JiraSeeder(settings, jira_client, scenario)
    git_seeder = GitSeeder(settings, guard, scenario, github=github)

    if exec_mode == ExecMode.DRY_RUN:
        existing = jira_seeder.existing_by_hint()
        planned = [t["hint"] for t in scenario["tickets"] if t["hint"] not in existing]
        click.echo("Dry run — nothing will be written.")
        click.echo(
            f"Jira project {scenario['jira']['project_key']}: "
            f"{len(existing)}/{len(scenario['tickets'])} seeded tickets already exist."
        )
        if planned:
            click.echo(f"Would create: {', '.join(planned)}")
        else:
            click.echo("Would create: nothing (board already converged).")
        click.echo(f"Sandbox repo initialized: {git_seeder.repo_initialized()}")
        return

    if exec_mode == ExecMode.PROPOSE:
        existing = jira_seeder.existing_by_hint()
        items: list[ChangeItem] = []
        if not git_seeder.repo_initialized():
            items.append(
                ChangeItem(
                    action="seed.repo",
                    subject="sandbox",
                    params={"base_branch": scenario["git"].get("base_branch", "main")},
                )
            )
        for ticket in scenario["tickets"]:
            if ticket["hint"] in existing:
                continue
            params: dict = {
                "summary": ticket["summary"],
                "status": ticket.get("status", ""),
            }
            branch = ticket.get("branch")
            if branch:
                params["branch"] = branch.get("name_template")
                params["commits"] = branch.get("commits", [])
                params["push"] = bool(branch.get("push"))
                if branch.get("pr"):
                    params["pr"] = branch["pr"]
            items.append(
                ChangeItem(action="seed.ticket", subject=ticket["hint"], params=params)
            )
        if not items:
            click.echo("Nothing to seed — board already converged. No changeset written.")
            return
        cs = propose_changeset(
            settings.artifacts_dir,
            items,
            description=(
                f"Seed demo board {scenario['jira']['project_key']} "
                f"from scenario v{scenario['scenario_version']}"
            ),
        )
        cs_hash = cs.compute_hash()
        click.echo(f"Proposed changeset {cs_hash} ({len(items)} items).")
        click.echo(
            "Review it, then run: groundtruth --mode apply "
            f"--changeset {cs_hash} --run-mode live seed"
        )
        return

    changeset_hash = ctx.obj["changeset"]
    load_changeset(settings.artifacts_dir, changeset_hash)
    run_dir = _new_run_dir(settings, "seed")
    ledger = LedgerWriter(run_dir / "ledger.jsonl")
    approval = _approval_ref(changeset_hash)

    tickets = jira_seeder.run(approval=approval)
    git_result = git_seeder.run(tickets, approval=approval)

    manifest = build_manifest(
        scenario, scenario["jira"]["project_key"], tickets, ledger.run_id
    )
    manifest["git"] = git_result
    _write_json(run_dir / "manifest.json", manifest)
    click.echo(
        f"Seeded {len(tickets)} tickets "
        f"({len(git_result['branches'])} branches). "
        f"Ledger + manifest: {run_dir}"
    )


@cli.command()
@exec_options
@click.pass_context
def reset(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
) -> None:
    """Tear down the synthetic board."""
    _merge_exec_options(ctx, mode, run_mode, changeset)
    try:
        _require_live(ctx, "reset")
        _run_reset(ctx)
    except (SeedError, JiraError, GitHubError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


def _run_reset(ctx: click.Context) -> None:
    settings = Settings.from_env()
    scenario = load_scenario()
    validate_against_settings(settings, scenario)
    guard, jira_client, github = _seed_stack(settings)
    resetter = Resetter(settings, jira_client, guard, scenario, github=github)
    exec_mode = ctx.obj["exec_mode"]

    plan = resetter.plan()

    if exec_mode == ExecMode.DRY_RUN:
        click.echo("Dry run — nothing will be deleted.")
        keys = ", ".join(i["key"] for i in plan["jira_issues"]) or "none"
        click.echo(f"Jira issues to delete ({len(plan['jira_issues'])}): {keys}")
        click.echo(f"GitHub repo: {plan['github_repo']}")
        click.echo(f"Local sandbox repo present: {plan['local_repo']}")
        return

    if exec_mode == ExecMode.PROPOSE:
        items: list[ChangeItem] = [
            ChangeItem(action="reset.jira", subject=i["key"])
            for i in plan["jira_issues"]
        ]
        if plan["github_repo"] == "ours":
            items.append(
                ChangeItem(action="reset.github_repo", subject=github.slug)
            )
        if plan["local_repo"]:
            items.append(
                ChangeItem(
                    action="reset.local_sandbox", subject=str(settings.workspace_dir)
                )
            )
        if not items:
            click.echo("Nothing to reset — no seeded state found.")
            return
        cs = propose_changeset(
            settings.artifacts_dir,
            items,
            description=f"Tear down seeded demo board {scenario['jira']['project_key']}",
        )
        cs_hash = cs.compute_hash()
        click.echo(f"Proposed changeset {cs_hash} ({len(items)} items).")
        click.echo(
            "Review it, then run: groundtruth --mode apply "
            f"--changeset {cs_hash} --run-mode live reset"
        )
        return

    changeset_hash = ctx.obj["changeset"]
    load_changeset(settings.artifacts_dir, changeset_hash)
    run_dir = _new_run_dir(settings, "reset")
    ledger = LedgerWriter(run_dir / "ledger.jsonl")
    approval = _approval_ref(changeset_hash)

    result = Resetter(
        settings, jira_client, guard, scenario, ledger=ledger, github=github
    ).run(approval=approval)
    _write_json(run_dir / "reset.json", result)
    click.echo(
        f"Reset: deleted {len(result['jira_deleted'])} Jira issues, "
        f"github repo {result['github_repo']}, "
        f"{result['local_entries_removed']} local entries. "
        f"Ledger: {run_dir}"
    )


# -- audit/score plumbing ------------------------------------------------------


_OBSERVER_ERRORS = (
    StewardError,
    JiraError,
    GitHubError,
    GitLogError,
    ReplayMiss,
    FixtureCorrupt,
    PolicyError,
    ChainVerificationError,
    RuntimeError,
)


def _steward_project_key(settings: Settings) -> str:
    if settings.jira_project_key:
        return settings.jira_project_key
    try:
        return str(load_scenario()["jira"]["project_key"])
    except (SeedError, OSError, KeyError):
        return ""


def _steward_stack(
    settings: Settings,
    run_mode: RunMode,
    ledger: LedgerWriter | None = None,
) -> BoardSteward:
    sandbox = settings.workspace_dir
    workspace_id = _workspace_identity(sandbox)
    slug = ""
    if settings.github_repo_owner and settings.github_repo_name:
        slug = f"{settings.github_repo_owner}/{settings.github_repo_name}"
    guard = GitGuard(sandbox, workspace_id, allowed_remote=slug)
    envelope = Envelope(mode=run_mode, store=FixtureStore(settings.fixtures_dir))
    return BoardSteward(
        settings=settings,
        envelope=envelope,
        jira=JiraClient(settings, envelope),
        gitlog=GitLog(envelope, guard),
        github=GitHubClient(settings, envelope, guard) if slug else None,
        project_key=_steward_project_key(settings),
        ledger=ledger,
    )


def _intake_stack(
    settings: Settings,
    run_mode: RunMode,
    ledger: LedgerWriter | None = None,
) -> IntakeAgent:
    sandbox = settings.workspace_dir
    workspace_id = _workspace_identity(sandbox)
    slug = ""
    if settings.github_repo_owner and settings.github_repo_name:
        slug = f"{settings.github_repo_owner}/{settings.github_repo_name}"
    guard = GitGuard(sandbox, workspace_id, allowed_remote=slug)
    envelope = Envelope(mode=run_mode, store=FixtureStore(settings.fixtures_dir))
    jira = JiraClient(settings, envelope)
    llm = LLMClient(settings, envelope)
    steward = BoardSteward(
        settings=settings,
        envelope=envelope,
        jira=jira,
        gitlog=GitLog(envelope, guard),
        github=GitHubClient(settings, envelope, guard) if slug else None,
        project_key=_steward_project_key(settings),
        ledger=ledger,
    )
    return IntakeAgent(
        settings=settings,
        jira=jira,
        llm=llm,
        steward=steward,
        ledger=ledger,
    )


def _require_intake_creds(settings: Settings) -> None:
    missing: list[str] = []
    if not settings.jira_base_url:
        missing.append("JIRA_BASE_URL")
    if not settings.jira_email:
        missing.append("JIRA_EMAIL")
    if not settings.jira_api_token:
        missing.append("JIRA_API_TOKEN")
    if not settings.llm_model:
        missing.append("LLM_MODEL")
    if missing:
        raise RuntimeError(
            f"Intake requires: {', '.join(missing)}. Set them in .env or environment."
        )


def _observer_settings(ctx: click.Context, command: str) -> Settings:
    if ctx.obj["exec_mode"] != ExecMode.DRY_RUN:
        raise click.UsageError(
            f"{command} is read-only: --mode is fixed to dry-run. "
            "Discrepancies and scores are reported, never applied."
        )
    settings = Settings.from_env()
    if ctx.obj["run_mode"] in (RunMode.LIVE, RunMode.RECORD):
        settings.validate_live_mode()
    return settings


def _ledger_mode_for(run_mode: RunMode) -> LedgerMode:
    return LedgerMode.REPLAY if run_mode is RunMode.REPLAY else LedgerMode.DRY_RUN


def _echo_discrepancies(discrepancies: list) -> None:
    for d in discrepancies:
        click.echo(f"[{d.type.value}] {d.severity.value} {d.subject}")
        for ev in d.evidence:
            click.echo(f"  evidence: {ev.kind.value} {ev.ref} {ev.url}")
        action = d.proposed_action
        target = f" {action.target}" if action.target else ""
        approval = "" if action.requires_approval else " (no approval needed)"
        click.echo(f"  proposed: {action.verb.value}{target}{approval}")


@cli.command()
@exec_options
@click.pass_context
def audit(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
) -> None:
    """Emit discrepancies with evidence."""
    _merge_exec_options(ctx, mode, run_mode, changeset)
    try:
        _run_audit(ctx)
    except _OBSERVER_ERRORS as exc:
        raise click.ClickException(str(exc)) from exc


def _run_audit(ctx: click.Context) -> None:
    settings = _observer_settings(ctx, "audit")
    run_mode = ctx.obj["run_mode"]
    run_dir = _new_run_dir(settings, "audit")
    ledger = LedgerWriter(run_dir / "ledger.jsonl")
    result = _steward_stack(settings, run_mode, ledger=ledger).audit()

    _write_json(
        run_dir / "discrepancies.json",
        {
            "run_id": ledger.run_id,
            "run_mode": run_mode.value,
            "project_key": result.board.project_key,
            "as_of": result.board.as_of,
            "policy_hash": result.policy.policy_hash,
            "board_snapshot_hash": board_snapshot_hash(result.board, result.repo),
            "discrepancies": [d.model_dump(mode="json") for d in result.discrepancies],
        },
    )
    click.echo(
        f"Audit {result.board.project_key} as of "
        f"{result.board.as_of.isoformat()} "
        f"(run-mode {run_mode.value}, policy {result.policy.policy_hash[:12]}...)"
    )
    if result.discrepancies:
        click.echo(f"{len(result.discrepancies)} discrepancies.")
        _echo_discrepancies(result.discrepancies)
    else:
        click.echo("No discrepancies — the board matches the repo.")
    click.echo(f"Ledger + discrepancies: {run_dir}")


@cli.command()
@exec_options
@click.pass_context
def score(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
) -> None:
    """Compute Board Truthfulness Score + evidence log."""
    _merge_exec_options(ctx, mode, run_mode, changeset)
    try:
        _run_score(ctx)
    except _OBSERVER_ERRORS as exc:
        raise click.ClickException(str(exc)) from exc


def _run_score(ctx: click.Context) -> None:
    settings = _observer_settings(ctx, "score")
    run_mode = ctx.obj["run_mode"]

    # Human-confirmed duplicate pairs live across all run ledgers; a broken
    # hash chain must surface here, not silently vanish from the score.
    ledger_entries: list[dict] = []
    for ledger_path in sorted(settings.artifacts_dir.glob("run_*/ledger.jsonl")):
        ledger_entries.extend(verify_chain(ledger_path))

    run_dir = _new_run_dir(settings, "score")
    ledger = LedgerWriter(run_dir / "ledger.jsonl")
    board, repo = _steward_stack(settings, run_mode, ledger=ledger).collect()
    # board.as_of is pinned by the steward's own (possibly frozen) clock.
    clock = FrozenClock(board.as_of)

    score = compute_score(board, repo, clock, ledger_entries=ledger_entries)
    control = compute_control_score(board, repo, clock, ledger_entries=ledger_entries)
    log_path = write_evidence_log(run_dir, score, control, run_id=ledger.run_id)
    score.evidence_log_path = str(log_path)
    if control is not None:
        control.evidence_log_path = str(log_path)

    _write_json(
        run_dir / "score.json",
        {
            "score": score.model_dump(mode="json"),
            "control_group": (
                control.model_dump(mode="json") if control is not None else None
            ),
        },
    )
    outputs_hash = hashlib.sha256(
        f"{score.total:.6f}|{score.board_snapshot_hash}".encode("utf-8")
    ).hexdigest()
    ledger.append(
        actor="scorer",
        action="score.run",
        mode=_ledger_mode_for(run_mode),
        subject=board.project_key,
        inputs_hash=score.policy_hash,
        outputs_hash=outputs_hash,
        evidence=[
            {
                "dimension": dim.name,
                "value": dim.value if dim.value is not None else "excluded",
            }
            for dim in score.dimensions
        ],
    )

    click.echo(render_score(score))
    if control is not None:
        click.echo("Control group (never touched by Delivery):")
        click.echo(render_score(control))
    click.echo(f"Ledger + score.json + evidence log: {run_dir}")


@cli.command()
@exec_options
@click.argument("file", type=click.Path(exists=True))
@click.pass_context
def intake(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
    file: str,
) -> None:
    """Raw text → tickets (propose, then apply)."""
    _merge_exec_options(ctx, mode, run_mode, changeset)
    try:
        _run_intake(ctx, Path(file))
    except (IntakeError, JiraError, StewardError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


def _run_intake(ctx: click.Context, file_path: Path) -> None:
    settings = Settings.from_env()
    run_mode = ctx.obj["run_mode"]
    settings.run_mode = run_mode
    if run_mode in (RunMode.LIVE, RunMode.RECORD):
        _require_intake_creds(settings)

    exec_mode = ctx.obj["exec_mode"]

    if exec_mode == ExecMode.DRY_RUN:
        agent = _intake_stack(settings, run_mode)
        result = agent.decompose(file_path)
        click.echo("Dry run — no tickets created.")
        click.echo(
            f"Decomposed {file_path.name}: "
            f"{len(result.accepted)} accepted, "
            f"{len(result.refused)} refused, "
            f"{len(result.duplicates)} duplicate suspect(s), "
            f"{len(result.rejected_raw)} rejected raw item(s)."
        )
        for story in result.accepted:
            click.echo(f"  ACCEPT  {story.summary} ({story.points} pts)")
        for story in result.refused:
            codes = ", ".join(story.dor.failures) if story.dor else "unknown"
            click.echo(f"  REFUSE  {story.summary} [{codes}]")
        return

    if exec_mode == ExecMode.PROPOSE:
        run_dir = _new_run_dir(settings, "intake")
        ledger = LedgerWriter(run_dir / "ledger.jsonl")
        agent = _intake_stack(settings, run_mode, ledger=ledger)
        cs = agent.propose(file_path)
        cs_hash = cs.compute_hash()
        click.echo(f"Proposed changeset {cs_hash} ({len(cs.items)} items).")
        click.echo(
            "Review it, then run: groundtruth --mode apply "
            f"--changeset {cs_hash} --run-mode {run_mode.value} intake {file_path}"
        )
        click.echo(f"Ledger: {run_dir}")
        return

    changeset_hash = ctx.obj["changeset"]
    load_changeset(settings.artifacts_dir, changeset_hash)
    run_dir = _new_run_dir(settings, "intake")
    ledger = LedgerWriter(run_dir / "ledger.jsonl")
    agent = _intake_stack(settings, run_mode, ledger=ledger)
    approval = _approval_ref(changeset_hash)
    created = agent.apply(
        load_changeset(settings.artifacts_dir, changeset_hash), approval, run_dir=run_dir
    )
    _write_json(
        run_dir / "created.json",
        {"created": [s.model_dump(mode="json") for s in created]},
    )
    click.echo(
        f"Created {len(created)} ticket(s). Rerun with the same changeset will create 0."
    )
    for story in created:
        click.echo(f"  {story.jira_key}: {story.summary}")
    click.echo(f"Ledger + created.json: {run_dir}")


@cli.command()
@exec_options
@click.option(
    "--capacity",
    type=int,
    default=None,
    help="Override sprint capacity (default: velocity from recent Done tickets).",
)
@click.option(
    "--assignees",
    type=str,
    default="",
    help="Comma-separated list of assignees for load balancing.",
)
@click.pass_context
def plan(
    ctx: click.Context,
    mode: str | None,
    run_mode: str | None,
    changeset: str | None,
    capacity: int | None,
    assignees: str,
) -> None:
    """Capacity-checked sprint proposal."""
    _merge_exec_options(ctx, mode, run_mode, changeset)
    try:
        _run_plan(ctx, capacity, assignees)
    except (PlannerError, StewardError, JiraError, GitHubError, GitLogError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


def _run_plan(
    ctx: click.Context, capacity: int | None, assignees_raw: str
) -> None:
    settings = _observer_settings(ctx, "plan")
    run_mode = ctx.obj["run_mode"]
    settings.run_mode = run_mode
    if run_mode in (RunMode.LIVE, RunMode.RECORD):
        settings.validate_live_mode()

    run_dir = _new_run_dir(settings, "plan")
    ledger = LedgerWriter(run_dir / "ledger.jsonl")
    steward = _steward_stack(settings, run_mode, ledger=ledger)
    board, repo = steward.collect()
    clock = FrozenClock(board.as_of)

    assignees = [a.strip() for a in assignees_raw.split(",") if a.strip()]
    planner = PlannerAgent(
        board,
        repo,
        clock,
        capacity=capacity,
        assignees=assignees,
        intake_state_path=settings.artifacts_dir / "intake_state.json",
    )
    plan = planner.build_plan()

    _write_json(run_dir / "plan.json", plan.model_dump(mode="json"))

    plan_json = plan.model_dump_json()
    outputs_hash = hashlib.sha256(plan_json.encode("utf-8")).hexdigest()
    ledger.append(
        actor="planner",
        action="plan.run",
        mode=_ledger_mode_for(run_mode),
        subject=board.project_key,
        inputs_hash=board_snapshot_hash(board, repo),
        outputs_hash=outputs_hash,
        evidence=[
            {
                "velocity": plan.velocity,
                "capacity": plan.capacity,
                "selected": len(plan.selected),
                "unscheduled": len(plan.unscheduled),
                "over_committed": plan.over_committed,
            }
        ],
    )

    click.echo(f"Sprint plan for {board.project_key} as of {board.as_of.isoformat()}")
    click.echo(
        f"Velocity: {plan.velocity}, capacity: {plan.capacity}, "
        f"selected: {plan.total_selected_points}/{plan.total_candidate_points} points"
    )
    if plan.over_committed:
        click.echo("WARNING: demand exceeds capacity.")
    if plan.cycles:
        click.echo(f"Dependency cycles detected: {len(plan.cycles)}")
        for cycle in plan.cycles:
            click.echo(f"  {' -> '.join(cycle)}")
    click.echo("Selected:")
    for ticket in plan.selected:
        owner = f" ({ticket.assignee})" if ticket.assignee else ""
        deps = f" [deps: {', '.join(ticket.depends_on)}]" if ticket.depends_on else ""
        click.echo(f"  {ticket.key}: {ticket.summary} — {ticket.points} pts{owner}{deps}")
    if plan.unscheduled:
        click.echo("Unscheduled:")
        for ticket in plan.unscheduled:
            click.echo(f"  {ticket.key}: {ticket.summary} — {ticket.points} pts")
    if plan.assignments:
        click.echo("Assignments:")
        for owner, keys in sorted(plan.assignments.items()):
            total = sum(t.points for t in plan.selected if t.key in keys)
            click.echo(f"  {owner}: {', '.join(keys)} ({total} pts)")
    click.echo(f"Ledger + plan.json: {run_dir}")


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
