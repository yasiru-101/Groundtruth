"""Repair loop: write source files, rerun tests, and enforce the test lock."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from groundtruth.adapters.llm import PromptName
from groundtruth.contracts.delivery import LockViolationRecord, RepairIteration
from groundtruth.contracts.story import AcceptanceCriterion
from groundtruth.contracts.testrun import TestOutcomeStatus, TestRunResult
from groundtruth.delivery.red_gate import classify as red_gate_classify
from groundtruth.delivery.test_lock import TestLock


class RepairError(Exception):
    pass


ALLOWED_ROOT_NAMES = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"}


def write_source_file(
    workspace: Path,
    rel_path: str,
    content: str,
    lock: TestLock,
    iteration: int = 0,
) -> list[LockViolationRecord]:
    """Single write primitive for source files.

    Allowed targets: files under ``src/`` or a small set of root config files.
    Forbids tests/, trace_manifest.json, .github/, and paths that escape the
    workspace.
    """
    rel_path = rel_path.replace("\\", "/")
    normalized = rel_path.lstrip("/")
    lowered = normalized.lower()

    violations: list[LockViolationRecord] = []
    forbidden = ("trace_manifest.json", ".github/")
    for token in forbidden:
        if token in lowered:
            violations.append(
                LockViolationRecord(
                    code="WRITE_OUTSIDE_SRC",
                    path=rel_path,
                    detail=f"writes to {token} are forbidden",
                    iteration=iteration,
                )
            )

    if normalized.startswith("tests/"):
        violations.append(
            LockViolationRecord(
                code="WRITE_OUTSIDE_SRC",
                path=rel_path,
                detail="implementation must not write to tests/",
                iteration=iteration,
            )
        )

    target = (workspace / normalized).resolve()
    workspace_resolved = workspace.resolve()
    if not target.is_relative_to(workspace_resolved):
        violations.append(
            LockViolationRecord(
                code="WRITE_OUTSIDE_SRC",
                path=rel_path,
                detail="path escapes workspace directory",
                iteration=iteration,
            )
        )

    parts = Path(normalized).parts
    if parts and parts[0] != "src" and normalized not in ALLOWED_ROOT_NAMES:
        violations.append(
            LockViolationRecord(
                code="WRITE_OUTSIDE_SRC",
                path=rel_path,
                detail="implementation files must live under src/ or be a known root file",
                iteration=iteration,
            )
        )

    if violations:
        return violations

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return []


def repair_loop(
    llm: Any,
    runner: Callable[[], TestRunResult],
    lock: TestLock,
    *,
    workspace: Path,
    ticket_key: str,
    summary: str,
    acceptance_criteria: list[AcceptanceCriterion],
    failing: list[str],
    bound_nodes: set[str],
    task: str = "repair",
    max_iterations: int = 3,
) -> list[RepairIteration]:
    """Run up to ``max_iterations`` LLM repair/implement attempts.

    Returns the full iteration history. ``green`` on the last iteration tells
    whether every bound node passed.
    """
    iterations: list[RepairIteration] = []

    for iteration in range(1, max_iterations + 1):
        run = runner()
        current_failing = sorted(
            node
            for node in bound_nodes
            if node not in run.collected_node_ids
            or run.tests.get(node) is None
            or run.tests[node].status != TestOutcomeStatus.PASSED
        )

        if not current_failing:
            iterations.append(
                RepairIteration(
                    iteration=iteration,
                    phase=task,
                    files_changed=[],
                    red_gate_valid=True,
                    green=True,
                )
            )
            break

        variables: dict[str, Any] = {
            "task": task,
            "ticket_key": ticket_key,
            "summary": summary,
            "acceptance_criteria": [
                {
                    "ac_id": ac.ac_id,
                    "given": ac.given,
                    "when": ac.when,
                    "then": ac.then,
                }
                for ac in acceptance_criteria
            ],
            "failing_tests": [
                {
                    "node_id": node,
                    "message": (
                        run.tests[node].message
                        if node in run.tests
                        else "node not collected"
                    ),
                }
                for node in current_failing
            ],
            "existing_files": _existing_source_files(workspace),
        }

        raw = llm.complete(PromptName.DELIVER_CODE, variables)
        payload = _parse_llm_response(raw)
        files = payload.get("files", [])
        diagnosis = payload.get("diagnosis", "")

        files_changed: list[str] = []
        violations: list[LockViolationRecord] = []

        for file_spec in files:
            rel_path = str(file_spec.get("path", ""))
            content = str(file_spec.get("content", ""))
            if "\r\n" in content:
                content = content.replace("\r\n", "\n")
            file_violations = write_source_file(
                workspace, rel_path, content, lock, iteration=iteration
            )
            if file_violations:
                violations.extend(file_violations)
            else:
                files_changed.append(rel_path)

        run_after = runner()
        lock_violations = _check_lock(lock, workspace, run_after, iteration)
        violations.extend(lock_violations)

        red_gate = red_gate_classify(run_after, bound_nodes)
        green = (
            all(
                node in run_after.collected_node_ids
                and run_after.tests.get(node) is not None
                and run_after.tests[node].status == TestOutcomeStatus.PASSED
                for node in bound_nodes
            )
            and bool(bound_nodes)
            and not violations
        )

        iterations.append(
            RepairIteration(
                iteration=iteration,
                phase=task,
                files_changed=files_changed,
                red_gate_valid=red_gate.is_valid_red,
                green=green,
                violations=violations,
                notes=[diagnosis] if diagnosis else [],
            )
        )

        if violations:
            lock.verify(iteration=iteration)

        if green:
            break

    return iterations


def _existing_source_files(workspace: Path) -> list[str]:
    src = workspace / "src"
    if not src.exists():
        return []
    return [str(p.relative_to(workspace)).replace("\\", "/") for p in src.rglob("*.py")]


def _parse_llm_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RepairError(f"LLM did not return valid JSON: {exc}") from exc


def _check_lock(
    lock: TestLock,
    workspace: Path,
    run: TestRunResult,
    iteration: int,
) -> list[LockViolationRecord]:
    violations: list[LockViolationRecord] = []
    test_dir = workspace / "tests"
    if test_dir.exists():
        for path in test_dir.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            violations.extend(lock.check_markers(content, path, iteration))
            violations.extend(lock.check_density(content, path, iteration))
    violations.extend(lock.verify(iteration=iteration))
    return violations
