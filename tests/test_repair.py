"""Adversarial tests for the repair loop and write guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundtruth.contracts.delivery import LockViolationRecord
from groundtruth.contracts.story import AcceptanceCriterion
from groundtruth.contracts.testrun import TestOutcome, TestOutcomeStatus, TestRunResult
from groundtruth.delivery.repair import RepairError, repair_loop, write_source_file
from groundtruth.delivery.test_lock import TestLock


def _run(collected: list[str], outcomes: dict[str, TestOutcomeStatus]) -> TestRunResult:
    return TestRunResult(
        run_id="run-1",
        exit_code=0,
        collected_node_ids=set(collected),
        tests={
            node: TestOutcome(node_id=node, status=status)
            for node, status in outcomes.items()
        },
    )


class TestWriteSourceFile:
    def test_allows_src_file(self, tmp_path: Path) -> None:
        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=tmp_path)
        violations = write_source_file(
            tmp_path, "src/app.py", "x = 1\n", lock, iteration=1
        )
        assert not violations
        assert (tmp_path / "src" / "app.py").read_text() == "x = 1\n"

    def test_forbids_tests_directory(self, tmp_path: Path) -> None:
        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=tmp_path)
        violations = write_source_file(
            tmp_path, "tests/test_x.py", "pass\n", lock, iteration=1
        )
        assert any(v.code == "WRITE_OUTSIDE_SRC" for v in violations)

    def test_forbids_trace_manifest(self, tmp_path: Path) -> None:
        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=tmp_path)
        violations = write_source_file(
            tmp_path, "trace_manifest.json", "{}\n", lock, iteration=1
        )
        assert any(v.code == "WRITE_OUTSIDE_SRC" for v in violations)

    def test_forbids_escape(self, tmp_path: Path) -> None:
        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=tmp_path)
        violations = write_source_file(
            tmp_path, "../evil.py", "pass\n", lock, iteration=1
        )
        assert any(v.code == "WRITE_OUTSIDE_SRC" for v in violations)


class TestRepairLoop:
    def test_green_on_first_iteration(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        class FakeLLM:
            def complete(self, name: str, variables: dict) -> str:
                return '{"files": [], "diagnosis": ""}'

        def runner() -> TestRunResult:
            return _run(
                ["tests/test_a.py::test_one"],
                {"tests/test_a.py::test_one": TestOutcomeStatus.PASSED},
            )

        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=workspace)
        iterations = repair_loop(
            FakeLLM(),
            runner,
            lock,
            workspace=workspace,
            ticket_key="AUTO-1",
            summary="test",
            acceptance_criteria=[
                AcceptanceCriterion(
                    ac_id="AUTO-1#1",
                    given="x",
                    when="y",
                    then="z",
                    raw="Given x When y Then z",
                )
            ],
            failing=[],
            bound_nodes={"tests/test_a.py::test_one"},
            task="implement",
        )
        assert iterations[-1].green
        assert iterations[-1].phase == "implement"

    def test_records_violation_when_llm_tries_to_write_tests(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        tests_dir = workspace / "tests"
        tests_dir.mkdir(parents=True)
        test_file = tests_dir / "test_a.py"
        test_file.write_text("def test_one():\n    assert False\n")

        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=workspace)
        lock.engage([test_file])

        class FakeLLM:
            def complete(self, name: str, variables: dict) -> str:
                return (
                    '{"files": [{"path": "tests/test_a.py", '
                    '"content": "def test_one():\\n    assert True\\n"}], '
                    '"diagnosis": ""}'
                )

        call_count = 0

        def runner() -> TestRunResult:
            nonlocal call_count
            call_count += 1
            status = (
                TestOutcomeStatus.FAILED
                if call_count == 1
                else TestOutcomeStatus.PASSED
            )
            return _run(
                ["tests/test_a.py::test_one"],
                {"tests/test_a.py::test_one": status},
            )

        try:
            iterations = repair_loop(
                FakeLLM(),
                runner,
                lock,
                workspace=workspace,
                ticket_key="AUTO-1",
                summary="test",
                acceptance_criteria=[
                    AcceptanceCriterion(
                        ac_id="AUTO-1#1",
                        given="x",
                        when="y",
                        then="z",
                        raw="Given x When y Then z",
                    )
                ],
                failing=["tests/test_a.py::test_one"],
                bound_nodes={"tests/test_a.py::test_one"},
                task="repair",
            )
            assert any(
                v.code == "WRITE_OUTSIDE_SRC"
                for it in iterations
                for v in it.violations
            )
        finally:
            lock.release()
