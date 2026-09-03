"""Tests for the delivery test lock."""

from __future__ import annotations

from pathlib import Path

import pytest

from groundtruth.contracts.delivery import LockViolationRecord
from groundtruth.delivery.test_lock import TestLock


class TestEngageRelease:
    def test_makes_files_readonly_and_restores_them(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        test_file = workspace / "tests" / "test_x.py"
        test_file.parent.mkdir()
        test_file.write_text("def test_one():\n    assert True\n")

        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=workspace)
        lock.engage([test_file])
        try:
            mode = test_file.stat().st_mode
            assert not mode & 0o200
        finally:
            lock.release()

        assert test_file.stat().st_mode & 0o200

    def test_restores_mutated_file(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        test_file = workspace / "tests" / "test_x.py"
        test_file.parent.mkdir()
        original = "def test_one():\n    assert True\n"
        test_file.write_text(original)

        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=workspace)
        lock.engage([test_file])
        try:
            lock.release()
            test_file.write_text("def test_one():\n    assert False\n")
            violations = lock.verify(iteration=1)
            assert violations
            assert violations[0].code == "TEST_MUTATION_ATTEMPT"
            assert test_file.read_text() == original
        finally:
            lock.release()


class TestCheckMonotonic:
    def test_reports_removed_nodes(self) -> None:
        lock = TestLock(run_dir=Path("/tmp/run"))
        violations = lock.check_monotonic(
            {"tests/test_a.py::one", "tests/test_a.py::two"},
            {"tests/test_a.py::one"},
            iteration=1,
        )
        assert len(violations) == 1
        assert violations[0].code == "TEST_COLLECTION_SHRANK"


class TestCheckMarkers:
    def test_detects_skip_marker(self) -> None:
        lock = TestLock(run_dir=Path("/tmp/run"))
        content = "import pytest\n@pytest.mark.skip\ndef test_one():\n    pass\n"
        violations = lock.check_markers(content, Path("test_x.py"), iteration=1)
        assert violations
        assert violations[0].code == "SKIP_MARKER_INJECTED"


class TestCheckDensity:
    def test_detects_assert_true(self) -> None:
        lock = TestLock(run_dir=Path("/tmp/run"))
        content = "def test_one():\n    assert True\n"
        violations = lock.check_density(content, Path("test_x.py"), iteration=1)
        codes = {v.code for v in violations}
        assert "TRIVIAL_ASSERTION" in codes

    def test_detects_no_asserts(self) -> None:
        lock = TestLock(run_dir=Path("/tmp/run"))
        content = "def test_one():\n    pass\n"
        violations = lock.check_density(content, Path("test_x.py"), iteration=1)
        assert any(v.code == "ASSERTION_DENSITY_DROPPED" for v in violations)

    def test_detects_raises_wrap(self) -> None:
        lock = TestLock(run_dir=Path("/tmp/run"))
        content = (
            "import pytest\n"
            "def test_one():\n"
            "    with pytest.raises(ValueError):\n"
            "        assert True\n"
        )
        violations = lock.check_density(content, Path("test_x.py"), iteration=1)
        assert any(v.code == "RAISES_WRAP" for v in violations)


class TestCheckWritePath:
    def test_forbids_manifest_and_github(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=workspace)

        v1 = lock.check_write_path("trace_manifest.json", iteration=1)
        assert any(v.code == "WRITE_OUTSIDE_SRC" for v in v1)

        v2 = lock.check_write_path(".github/workflows/ci.yml", iteration=1)
        assert any(v.code == "WRITE_OUTSIDE_SRC" for v in v2)

    def test_forbids_escape(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        lock = TestLock(run_dir=tmp_path / "run", workspace_dir=workspace)
        violations = lock.check_write_path("../evil.py", iteration=1)
        assert any(v.code == "WRITE_OUTSIDE_SRC" for v in violations)
