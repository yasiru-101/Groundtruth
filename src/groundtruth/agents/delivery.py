"""Delivery Agent: acceptance criteria to a guarded pull request."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from groundtruth.adapters.github import GitHubClient
from groundtruth.adapters.jira import JiraClient, adf_to_text
from groundtruth.adapters.llm import LLMClient
from groundtruth.adapters.pytest_runner import run_tests
from groundtruth.config import RunMode, Settings
from groundtruth.contracts.delivery import DeliveryPhase, DeliveryResult, RedGateReport
from groundtruth.contracts.ledger import ApprovalRef, LedgerMode, LedgerOutcome
from groundtruth.contracts.testrun import TestOutcomeStatus, TestRunResult
from groundtruth.contracts.trace import TraceMatrixRow
from groundtruth.delivery.pr_body import render as render_pr_body
from groundtruth.delivery.red_gate import classify as classify_red_gate
from groundtruth.delivery.repair import repair_loop
from groundtruth.delivery.test_author import author_tests
from groundtruth.delivery.test_lock import TestLock
from groundtruth.ids import branch_slug, content_hash
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.safety.git_guard import GitGuard
from groundtruth.scoring.ac_parser import parse_acceptance_criteria
from groundtruth.trace.manifest import latest_trace_manifest
from groundtruth.trace.reconcile import (
    build_manifest,
    canonical_bytes,
    merge_bindings,
    reconcile,
)


class DeliveryError(Exception):
    pass


_CI_WORKFLOW = """name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: \"3.13\"
      - run: python -m pip install -e .[dev]
      - run: python -m pytest
"""

_SAFE_JIRA_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class DeliveryAgent:
    """Deliver one non-control Jira ticket through an auditable test-first flow."""

    def __init__(
        self,
        settings: Settings,
        jira: JiraClient,
        llm: LLMClient,
        guard: GitGuard,
        github: GitHubClient | None,
        ledger: LedgerWriter | None = None,
        approval: ApprovalRef | None = None,
    ) -> None:
        self._settings = settings
        self._jira = jira
        self._llm = llm
        self._guard = guard
        self._github = github
        self._ledger = ledger
        self._approval = approval
        self._test_run_count = 0

    def deliver(self, key: str, run_dir: Path | None = None) -> DeliveryResult:
        if not _SAFE_JIRA_KEY.fullmatch(key):
            raise DeliveryError(f"Invalid Jira key: {key!r}")
        if self._github is None or not self._github.slug.strip("/"):
            raise DeliveryError("Delivery requires a configured GitHub repository.")

        run_dir = run_dir or self._new_run_dir()
        branch = f"deliver/{branch_slug(key)}"
        red_gate = RedGateReport()
        issue = self._jira.get_issue(key, fields=["summary", "description", "labels"])
        fields = issue.get("fields") or {}
        labels = [str(label) for label in fields.get("labels") or []]

        if "gt-control" in labels:
            return self._finish(
                DeliveryResult(
                    ticket_key=key,
                    branch=branch,
                    phase=DeliveryPhase.BRANCH,
                    red_gate=red_gate,
                    refusals=["Control-group tickets cannot be delivered."],
                    run_dir=str(run_dir),
                ),
                outcome=LedgerOutcome.REFUSED,
            )

        description_doc = fields.get("description")
        description = adf_to_text(description_doc) if description_doc else ""
        summary = str(fields.get("summary") or "")
        criteria = parse_acceptance_criteria(key, description)
        if not criteria or any(not criterion.is_wellformed for criterion in criteria):
            return self._finish(
                DeliveryResult(
                    ticket_key=key,
                    branch=branch,
                    phase=DeliveryPhase.AUTHOR_TESTS,
                    red_gate=red_gate,
                    refusals=["Ticket has no well-formed Given/When/Then acceptance criteria."],
                    run_dir=str(run_dir),
                ),
                outcome=LedgerOutcome.REFUSED,
            )

        dirty = self._guard.run(["git", "status", "--porcelain"]).stdout.strip()
        if dirty:
            return self._finish(
                DeliveryResult(
                    ticket_key=key,
                    branch=branch,
                    phase=DeliveryPhase.BRANCH,
                    red_gate=red_gate,
                    refusals=["Workspace is not clean; delivery will not stage unrelated changes."],
                    notes=[dirty],
                    run_dir=str(run_dir),
                ),
                outcome=LedgerOutcome.REFUSED,
            )

        branch_exists = self._branch_exists(branch)
        self._guard.run(
            ["git", "checkout", branch] if branch_exists else ["git", "checkout", "-b", branch]
        )
        if branch_exists:
            existing = self._existing_delivery(key, branch, run_dir)
            if existing is not None:
                return existing
            return self._finish(
                DeliveryResult(
                    ticket_key=key,
                    branch=branch,
                    phase=DeliveryPhase.BRANCH,
                    red_gate=red_gate,
                    refusals=["Delivery branch already exists without a pull request."],
                    run_dir=str(run_dir),
                ),
                outcome=LedgerOutcome.REFUSED,
            )

        authored = author_tests(
            self._llm,
            key,
            summary,
            description,
            criteria,
            self._settings.workspace_dir,
            existing_tests=self._test_files(),
        )
        bound_nodes = {binding.test_node_id for binding in authored.bindings}
        red_run = self._run_tests(run_dir, "red")
        red_gate = classify_red_gate(red_run, bound_nodes)
        if not red_gate.is_valid_red:
            (self._settings.workspace_dir / authored.test_file).unlink(missing_ok=True)
            return self._finish(
                DeliveryResult(
                    ticket_key=key,
                    branch=branch,
                    phase=DeliveryPhase.RED_GATE,
                    red_gate=red_gate,
                    refusals=["Red gate failed: every bound test must fail by assertion."],
                    run_dir=str(run_dir),
                ),
                outcome=LedgerOutcome.REFUSED,
            )

        lock = TestLock(run_dir=run_dir, workspace_dir=self._settings.workspace_dir)
        lock.engage(self._test_paths())
        try:
            self._stage_and_commit([authored.test_file], f"test({key}): add acceptance coverage")

            iterations = repair_loop(
                self._llm,
                lambda: self._run_tests(run_dir, "implement"),
                lock,
                workspace=self._settings.workspace_dir,
                ticket_key=key,
                summary=summary,
                acceptance_criteria=criteria,
                failing=sorted(bound_nodes),
                bound_nodes=bound_nodes,
                task="implement",
                max_iterations=1,
            )
            if not iterations[-1].green:
                repairs = repair_loop(
                    self._llm,
                    lambda: self._run_tests(run_dir, "repair"),
                    lock,
                    workspace=self._settings.workspace_dir,
                    ticket_key=key,
                    summary=summary,
                    acceptance_criteria=criteria,
                    failing=sorted(bound_nodes),
                    bound_nodes=bound_nodes,
                    task="repair",
                    max_iterations=3,
                )
                iterations.extend(
                    repair.model_copy(update={"iteration": len(iterations) + index})
                    for index, repair in enumerate(repairs, start=1)
                )

            final_run = self._run_tests(run_dir, "final")
            report = reconcile(authored.bindings, final_run)
            green = self._bound_nodes_pass(final_run, report.bound_node_ids)
            rows = self._matrix_rows(criteria, report.rows)

            prior = latest_trace_manifest(self._settings.artifacts_dir)
            merged_bindings = merge_bindings(
                prior.bindings if prior else [], authored.bindings, key
            )
            manifest = build_manifest(
                run_dir.name,
                datetime.now(timezone.utc),
                merged_bindings,
                final_run,
            )
            manifest_bytes = canonical_bytes(manifest)
            workspace_manifest = self._settings.workspace_dir / "trace_manifest.json"
            workspace_manifest.write_bytes(manifest_bytes)
            (run_dir / "trace_manifest.json").write_bytes(manifest_bytes)

            source_files = self._changed_source_files(iterations)
            self._stage_and_commit(
                [*source_files, "trace_manifest.json"],
                f"feat({key}): implement acceptance criteria",
            )

            workflow_path = self._settings.workspace_dir / ".github" / "workflows" / "ci.yml"
            workflow_added = self._ensure_ci_workflow(workflow_path)
            if workflow_added:
                self._stage_and_commit(
                    [".github/workflows/ci.yml"], "ci: add test workflow"
                )

            head_sha = self._guard.run(["git", "rev-parse", "HEAD"]).stdout.strip()
            self._guard.run(["git", "push", "-u", "origin", branch])

            provisional = DeliveryResult(
                ticket_key=key,
                branch=branch,
                phase=DeliveryPhase.PUSH,
                red_gate=red_gate,
                iterations=iterations,
                green=green,
                draft=not green,
                head_sha=head_sha,
                unrelated_failures=report.unbound_failures,
                run_dir=str(run_dir),
            )
            body_path = run_dir / "pr_body.md"
            body_path.write_text(
                render_pr_body(provisional, rows), encoding="utf-8", newline="\n"
            )
            pr_url = self._github.pr_create(
                title=f"{key}: {summary}",
                head=branch,
                base="main",
                draft=not green,
                body_file=body_path,
            )
            return self._finish(
                provisional.model_copy(update={"phase": DeliveryPhase.PR, "pr_url": pr_url})
            )
        finally:
            lock.release()

    def _existing_delivery(
        self, key: str, branch: str, run_dir: Path
    ) -> DeliveryResult | None:
        for pull_request in self._github.pr_list(state="all"):
            if pull_request.get("headRefName") != branch:
                continue
            run = self._run_tests(run_dir, "idempotency")
            manifest = latest_trace_manifest(self._settings.artifacts_dir)
            bindings = [
                binding
                for binding in (manifest.bindings if manifest else [])
                if binding.ac_id.startswith(f"{key}#")
            ]
            report = reconcile(bindings, run)
            green = self._bound_nodes_pass(run, report.bound_node_ids)
            return self._finish(
                DeliveryResult(
                    ticket_key=key,
                    branch=branch,
                    phase=DeliveryPhase.PR,
                    red_gate=RedGateReport(),
                    green=green,
                    pr_url=str(pull_request.get("url") or "") or None,
                    draft=not green,
                    head_sha=self._guard.run(["git", "rev-parse", "HEAD"]).stdout.strip() or None,
                    unrelated_failures=report.unbound_failures,
                    notes=["Existing delivery pull request reused."],
                    run_dir=str(run_dir),
                )
            )
        return None

    def _run_tests(self, run_dir: Path, label: str) -> TestRunResult:
        self._test_run_count += 1
        report_path = run_dir / "pytest" / f"{self._test_run_count:02d}_{label}.json"
        return run_tests(cwd=self._settings.workspace_dir, report_path=report_path)

    def _new_run_dir(self) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_dir = self._settings.artifacts_dir / f"run_{stamp}_deliver"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _branch_exists(self, branch: str) -> bool:
        output = self._guard.run(["git", "branch", "--list", branch]).stdout
        return any(line.strip().lstrip("*").strip() == branch for line in output.splitlines())

    def _test_paths(self) -> list[Path]:
        test_dir = self._settings.workspace_dir / "tests"
        return sorted(test_dir.rglob("*.py")) if test_dir.exists() else []

    def _test_files(self) -> list[str]:
        workspace = self._settings.workspace_dir
        return [str(path.relative_to(workspace)).replace("\\", "/") for path in self._test_paths()]

    @staticmethod
    def _bound_nodes_pass(run: TestRunResult, bound_nodes: set[str]) -> bool:
        return bool(bound_nodes) and all(
            node in run.collected_node_ids
            and run.tests.get(node) is not None
            and run.tests[node].status == TestOutcomeStatus.PASSED
            for node in bound_nodes
        )

    @staticmethod
    def _matrix_rows(criteria: list, rows: list[TraceMatrixRow]) -> list[TraceMatrixRow]:
        ac_text = {criterion.ac_id: criterion.raw for criterion in criteria}
        return [row.model_copy(update={"ac_text": ac_text.get(row.ac_id, "")}) for row in rows]

    @staticmethod
    def _changed_source_files(iterations: Iterable) -> list[str]:
        files = {
            path.replace("\\", "/")
            for iteration in iterations
            for path in iteration.files_changed
        }
        return sorted(files)

    def _stage_and_commit(self, paths: list[str], message: str) -> None:
        unique_paths = list(dict.fromkeys(path for path in paths if path))
        if not unique_paths:
            return
        self._guard.run(["git", "add", *unique_paths])
        staged = self._guard.run(["git", "diff", "--cached", "--quiet"], check=False)
        if staged.returncode != 0:
            self._guard.run(["git", "commit", "-m", message])

    @staticmethod
    def _ensure_ci_workflow(path: Path) -> bool:
        if path.exists():
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_CI_WORKFLOW, encoding="utf-8", newline="\n")
        return True

    def _finish(
        self, result: DeliveryResult, outcome: LedgerOutcome = LedgerOutcome.OK
    ) -> DeliveryResult:
        run_dir = Path(result.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "delivery_result.json").write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
            newline="\n",
        )
        if self._ledger is not None:
            self._ledger.append(
                actor="delivery",
                action="delivery.deliver",
                mode=LedgerMode.REPLAY if self._settings.run_mode is RunMode.REPLAY else LedgerMode.APPLY,
                subject=result.ticket_key,
                inputs_hash=content_hash(result.ticket_key, result.branch),
                outputs_hash=content_hash(result.model_dump_json()),
                evidence=[
                    {
                        "branch": result.branch,
                        "head_sha": result.head_sha or "",
                        "pr_url": result.pr_url or "",
                        "green": result.green,
                    }
                ],
                approval=self._approval,
                outcome=outcome,
                error="; ".join(result.refusals) or None,
            )
        return result
