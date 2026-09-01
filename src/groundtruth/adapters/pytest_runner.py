"""pytest runner: subprocess pytest --json-report -> TestRunResult.

Runs pytest in the target repo with the pytest-json-report plugin and parses
the machine-readable report. If the plugin is unavailable (usage-error exit
with no report file), falls back to --junit-xml and reconstructs node ids
from the xunit1 ``file``/``classname``/``name`` attributes.

Not behind the record/replay envelope: pytest is a local, deterministic
ground-truth generator — its raw reports are persisted as artifacts by the
caller instead.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from groundtruth.contracts.testrun import (
    TestOutcome,
    TestOutcomeStatus,
    TestRunResult,
)


class PytestRunnerError(Exception):
    pass


_OUTCOME_MAP = {
    "passed": TestOutcomeStatus.PASSED,
    "failed": TestOutcomeStatus.FAILED,
    "skipped": TestOutcomeStatus.SKIPPED,
    "xfailed": TestOutcomeStatus.SKIPPED,
    "xpassed": TestOutcomeStatus.PASSED,
    "error": TestOutcomeStatus.ERROR,
}


def _outcome_from_json(entry: dict[str, Any]) -> tuple[TestOutcomeStatus, str, float]:
    call = entry.get("call") or {}
    setup = entry.get("setup") or {}
    teardown = entry.get("teardown") or {}

    duration = (
        setup.get("duration", 0.0) + call.get("duration", 0.0) + teardown.get("duration", 0.0)
    )

    message = ""
    crash = call.get("crash") or setup.get("crash") or teardown.get("crash")
    if crash:
        message = str(crash.get("message", ""))
    elif call.get("longrepr"):
        message = str(call["longrepr"])[:2000]

    raw_outcome = entry.get("outcome", "error")
    status = _OUTCOME_MAP.get(raw_outcome, TestOutcomeStatus.ERROR)
    return status, message, duration


def _parse_json_report(report: dict[str, Any], run_id: str, report_path: Path) -> TestRunResult:
    tests: dict[str, TestOutcome] = {}
    collected: set[str] = set()

    for entry in report.get("tests", []):
        node_id = entry.get("nodeid", "")
        if not node_id:
            continue
        collected.add(node_id)
        status, message, duration = _outcome_from_json(entry)
        tests[node_id] = TestOutcome(
            node_id=node_id, status=status, duration=duration, message=message
        )

    return TestRunResult(
        run_id=run_id,
        exit_code=int(report.get("exitcode", -1)),
        tests=tests,
        collected_node_ids=collected,
        raw_report_path=str(report_path),
    )


def _nodeid_from_junit(file: str, classname: str, name: str) -> str:
    file = file.replace("\\", "/")
    if not file:
        return f"{classname}::{name}" if classname else name
    node_id = file
    tail = classname
    if file.endswith(".py"):
        module = file[:-3].replace("/", ".")
        if tail.startswith(module):
            tail = tail[len(module):].strip(".")
    if tail:
        node_id += f"::{tail}"
    node_id += f"::{name}"
    return node_id


def _parse_junit_report(xml_path: Path, run_id: str, exit_code: int) -> TestRunResult:
    tests: dict[str, TestOutcome] = {}
    collected: set[str] = set()

    tree = ET.parse(xml_path)
    for testcase in tree.iter("testcase"):
        file = testcase.get("file", "")
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        node_id = _nodeid_from_junit(file, classname, name)

        status = TestOutcomeStatus.PASSED
        message = ""
        for child in testcase:
            if child.tag == "failure":
                status = TestOutcomeStatus.FAILED
                message = child.get("message", "") or (child.text or "")[:2000]
            elif child.tag == "error":
                status = TestOutcomeStatus.ERROR
                message = child.get("message", "") or (child.text or "")[:2000]
            elif child.tag == "skipped":
                status = TestOutcomeStatus.SKIPPED
                message = child.get("message", "")

        duration = float(testcase.get("time", "0") or 0)
        collected.add(node_id)
        tests[node_id] = TestOutcome(
            node_id=node_id, status=status, duration=duration, message=message
        )

    return TestRunResult(
        run_id=run_id,
        exit_code=exit_code,
        tests=tests,
        collected_node_ids=collected,
        raw_report_path=str(xml_path),
    )


def _invoke(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            shell=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise PytestRunnerError(
            f"pytest timed out after {timeout}s: {' '.join(cmd)}"
        ) from exc


def run_tests(
    test_paths: list[str] | None = None,
    *,
    cwd: Path,
    report_path: Path | None = None,
    timeout: int = 600,
) -> TestRunResult:
    """Run pytest in ``cwd`` and return a parsed TestRunResult.

    ``report_path`` persists the raw machine-readable report (needed as PR
    evidence); when omitted a temp file is used and deleted after parsing.
    """
    run_id = uuid.uuid4().hex[:12]
    temp_dir: tempfile.TemporaryDirectory | None = None

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        json_report = report_path
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="gt-pytest-")
        json_report = Path(temp_dir.name) / "report.json"

    try:
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *(test_paths or []),
            "-p",
            "no:cacheprovider",
            "--json-report",
            f"--json-report-file={json_report}",
        ]
        result = _invoke(cmd, cwd, timeout)

        if json_report.exists():
            try:
                report = json.loads(json_report.read_text(encoding="utf-8"))
                return _parse_json_report(report, run_id, json_report)
            except (json.JSONDecodeError, OSError) as exc:
                raise PytestRunnerError(
                    f"pytest json report unreadable at {json_report}: {exc}"
                ) from exc

        # Plugin absent (usage error, no report file) -> junit fallback.
        if temp_dir is not None:
            junit_report = Path(temp_dir.name) / "report.xml"
        else:
            junit_report = report_path.with_suffix(".xml")

        fallback_cmd = [
            sys.executable,
            "-m",
            "pytest",
            *(test_paths or []),
            "-p",
            "no:cacheprovider",
            "--junitxml",
            str(junit_report),
            "--junit-family",
            "xunit1",
        ]
        fallback_result = _invoke(fallback_cmd, cwd, timeout)
        if junit_report.exists():
            return _parse_junit_report(junit_report, run_id, fallback_result.returncode)

        raise PytestRunnerError(
            "pytest produced neither a json report nor junit xml. "
            f"stdout: {result.stdout[-2000:]!r} stderr: {result.stderr[-2000:]!r}"
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
