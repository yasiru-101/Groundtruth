"""Enforcement test: git subprocess calls must only appear in git_guard.py.

This is the single-choke-point guarantee from the spec:
"safety/git_guard.py is the only module permitted to invoke git,
enforced by a test that greps the tree for git subprocess calls
outside it and fails."
"""

from __future__ import annotations

import re
from pathlib import Path

from groundtruth.config import PROJECT_ROOT

SRC_DIR = PROJECT_ROOT / "src" / "groundtruth"
ALLOWED_FILES = {
    "git_guard.py",
}

GIT_SUBPROCESS_PATTERNS = [
    re.compile(r'subprocess\.\w+\(\s*\[?\s*["\']git["\']'),
    re.compile(r'subprocess\.\w+\(\s*\[?\s*["\']gh["\']'),
    re.compile(r'os\.system\s*\(\s*["\']git\b'),
    re.compile(r'os\.popen\s*\(\s*["\']git\b'),
    re.compile(r'shell\s*=\s*True'),
]


def _find_git_calls(path: Path) -> list[tuple[int, str, str]]:
    violations: list[tuple[int, str, str]] = []
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    for line_no, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for pattern in GIT_SUBPROCESS_PATTERNS:
            if pattern.search(line):
                violations.append((line_no, pattern.pattern, line.strip()))
    return violations


def test_no_git_calls_outside_guard() -> None:
    violations_by_file: dict[str, list[tuple[int, str, str]]] = {}

    for py_file in SRC_DIR.rglob("*.py"):
        if py_file.name in ALLOWED_FILES:
            continue
        file_violations = _find_git_calls(py_file)
        if file_violations:
            rel = py_file.relative_to(SRC_DIR)
            violations_by_file[str(rel)] = file_violations

    if violations_by_file:
        details = []
        for filepath, violations in violations_by_file.items():
            for line_no, pattern, line in violations:
                details.append(f"  {filepath}:{line_no} matched {pattern!r}: {line}")
        msg = (
            "Git subprocess calls found outside git_guard.py:\n"
            + "\n".join(details)
        )
        raise AssertionError(msg)


def test_no_shell_true_anywhere() -> None:
    violations: list[str] = []
    pattern = re.compile(r'shell\s*=\s*True')

    for py_file in SRC_DIR.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        for line_no, line in enumerate(content.splitlines(), 1):
            if pattern.search(line):
                rel = py_file.relative_to(SRC_DIR)
                violations.append(f"  {rel}:{line_no}: {line.strip()}")

    if violations:
        raise AssertionError(
            "shell=True found in source:\n" + "\n".join(violations)
        )
