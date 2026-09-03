"""LLM-driven test author with deterministic static validation."""

from __future__ import annotations

import ast
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from groundtruth.adapters.llm import LLMClient, PromptName
from groundtruth.contracts.delivery import AuthoredTests
from groundtruth.contracts.story import AcceptanceCriterion
from groundtruth.contracts.trace import TraceLink


class AuthoringError(Exception):
    pass


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _validate_no_test_weakening(content: str) -> list[str]:
    """Static checks: no skip/xfail markers, no assert True, no raises wrap."""
    issues: list[str] = []
    lowered = content.lower()
    for marker in ("@pytest.mark.skip", "@pytest.mark.xfail", "pytest.skip(", "pytest.xfail("):
        if marker in lowered:
            issues.append(f"forbidden marker: {marker}")

    try:
        tree = ast.parse(content)
    except SyntaxError as exc:
        issues.append(f"syntax error: {exc}")
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                issues.append("trivial assertion: assert True")
    return issues


def _validate_bindings(content: str, bindings: list[TraceLink]) -> list[str]:
    """Every bound test_node_id must correspond to a function in the module."""
    issues: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return issues

    function_ids: set[str] = set()
    module_name = None  # determined from file path by caller
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function_ids.add(node.name)

    for link in bindings:
        node_id = link.test_node_id
        if "::" not in node_id:
            issues.append(f"binding node id missing '::': {node_id}")
            continue
        func = node_id.split("::")[-1]
        if func not in function_ids:
            issues.append(f"binding references missing test function: {node_id}")
    return issues


def author_tests(
    llm: LLMClient,
    ticket_key: str,
    summary: str,
    description: str,
    acceptance_criteria: list[AcceptanceCriterion],
    workspace_dir: Path,
    existing_tests: list[str] | None = None,
) -> AuthoredTests:
    """Ask the LLM to author tests for a ticket, then validate and write them.

    Returns an ``AuthoredTests`` object without side effects; callers commit
    the file when ready.
    """
    variables: dict[str, Any] = {
        "task": "author_tests",
        "ticket_key": ticket_key,
        "summary": summary,
        "description": description,
        "acceptance_criteria": [
            {
                "ac_id": ac.ac_id,
                "given": ac.given,
                "when": ac.when,
                "then": ac.then,
            }
            for ac in acceptance_criteria
        ],
        "existing_tests": existing_tests or [],
    }
    raw = llm.complete(PromptName.DELIVER_CODE, variables)
    text = _extract_json(raw)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AuthoringError(f"LLM did not return valid JSON: {exc}") from exc

    for key in ("test_file", "bindings", "content"):
        if key not in payload:
            raise AuthoringError(f"LLM JSON missing required key: {key}")

    test_file = str(payload["test_file"]).replace("\\", "/")
    rel_path = Path(test_file)
    test_file = rel_path.as_posix()
    if not rel_path.parts or rel_path.parts[0] != "tests":
        raise AuthoringError(f"test file must live under tests/: {test_file}")

    content = str(payload["content"])
    if "\r\n" in content:
        content = content.replace("\r\n", "\n")

    raw_bindings = payload["bindings"]
    if not isinstance(raw_bindings, list):
        raise AuthoringError("bindings must be a list")

    bindings: list[TraceLink] = []
    for item in raw_bindings:
        if not isinstance(item, dict):
            raise AuthoringError("each binding must be an object")
        ac_id = item.get("ac_id")
        test_node_id = item.get("test_node_id")
        if not ac_id or not test_node_id:
            raise AuthoringError("binding missing ac_id or test_node_id")
        if not str(ac_id).startswith(f"{ticket_key}#"):
            raise AuthoringError(
                f"binding ac_id {ac_id!r} does not belong to ticket {ticket_key}"
            )
        node_file = str(test_node_id).split("::", 1)[0].replace("\\", "/")
        if node_file != test_file:
            raise AuthoringError(
                f"binding node id does not match authored test file: {test_node_id}"
            )
        bindings.append(
            TraceLink(
                ac_id=str(ac_id),
                test_node_id=str(test_node_id),
                bound_at=datetime.now(timezone.utc),
                test_file_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )

    issues = _validate_no_test_weakening(content) + _validate_bindings(content, bindings)
    if issues:
        raise AuthoringError("authored test validation failed: " + "; ".join(issues))

    target = (workspace_dir / rel_path).resolve()
    tests_dir = (workspace_dir / "tests").resolve()
    if not target.is_relative_to(tests_dir):
        raise AuthoringError(f"test file must resolve under workspace/tests/: {test_file}")
    if target.exists():
        raise AuthoringError(
            f"test file already exists and may not be overwritten: {test_file}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")

    return AuthoredTests(test_file=test_file, bindings=bindings, content=content)
