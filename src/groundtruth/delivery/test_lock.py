"""Test lock: make test files read-only during implementation and detect
attempts to weaken or mutate them.
"""

from __future__ import annotations

import ast
import hashlib
import shutil
import stat
from pathlib import Path
from typing import Any

from groundtruth.contracts.delivery import LockViolationRecord


VIOLATION_CODES = {
    "TEST_MUTATION_ATTEMPT",
    "TEST_COLLECTION_SHRANK",
    "SKIP_MARKER_INJECTED",
    "ASSERTION_DENSITY_DROPPED",
    "TRIVIAL_ASSERTION",
    "RAISES_WRAP",
    "WRITE_OUTSIDE_SRC",
}


class TestLock:
    __test__ = False

    def __init__(self, run_dir: Path, workspace_dir: Path | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.locked_dir = self.run_dir / "locked"
        self.workspace_dir = Path(workspace_dir) if workspace_dir else None
        self.paths: list[Path] = []
        self._hashes: dict[Path, str] = {}

    @staticmethod
    def _hash_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _make_readonly(path: Path) -> None:
        path.chmod(stat.S_IREAD)

    @staticmethod
    def _make_writable(path: Path) -> None:
        path.chmod(stat.S_IWRITE | stat.S_IREAD)

    def engage(self, paths: list[Path]) -> None:
        """Snapshot test files, copy them into the run directory, and make the
        originals read-only.
        """
        self.paths = [Path(p).resolve() for p in paths]
        self._hashes = {}
        if self.locked_dir.exists():
            shutil.rmtree(self.locked_dir)
        self.locked_dir.mkdir(parents=True, exist_ok=True)

        for path in self.paths:
            if not path.exists():
                continue
            digest = self._hash_file(path)
            self._hashes[path] = digest
            backup = self.locked_dir / digest / path.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            self._make_readonly(path)

    def release(self) -> None:
        """Restore write permissions on all locked files."""
        for path in self.paths:
            if path.exists():
                try:
                    self._make_writable(path)
                except OSError:
                    pass

    def verify(self, iteration: int = 0) -> list[LockViolationRecord]:
        """Rehash locked files. If a file changed, restore it from the locked
        copy and emit a ``TEST_MUTATION_ATTEMPT`` violation.
        """
        violations: list[LockViolationRecord] = []
        for path in self.paths:
            if not path.exists():
                # Try to restore from the most recent backup.
                backups = sorted(self.locked_dir.glob(f"*/{path.name}"))
                if backups:
                    backup = backups[-1]
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, path)
                    self._make_readonly(path)
                violations.append(
                    LockViolationRecord(
                        code="TEST_MUTATION_ATTEMPT",
                        path=str(path),
                        detail="test file was deleted during implementation",
                        iteration=iteration,
                    )
                )
                continue

            current = self._hash_file(path)
            expected = self._hashes.get(path)
            if expected and current != expected:
                backup_dir = self.locked_dir / expected
                backup = backup_dir / path.name
                if backup.exists():
                    self._make_writable(path)
                    shutil.copy2(backup, path)
                    self._make_readonly(path)
                violations.append(
                    LockViolationRecord(
                        code="TEST_MUTATION_ATTEMPT",
                        path=str(path),
                        detail=f"hash changed: {current[:16]}... != {expected[:16]}...",
                        iteration=iteration,
                    )
                )
        return violations

    def check_monotonic(
        self,
        before: set[str],
        after: set[str],
        iteration: int,
    ) -> list[LockViolationRecord]:
        """The set of collected test node ids must not shrink."""
        violations: list[LockViolationRecord] = []
        removed = sorted(before - after)
        for node_id in removed:
            violations.append(
                LockViolationRecord(
                    code="TEST_COLLECTION_SHRANK",
                    path=node_id,
                    detail="test node removed after red gate",
                    iteration=iteration,
                )
            )
        return violations

    def check_markers(
        self,
        content: str,
        path: Path,
        iteration: int,
    ) -> list[LockViolationRecord]:
        """Detect skip/xfail markers that would neutralize tests."""
        violations: list[LockViolationRecord] = []
        lowered = content.lower()
        for marker in ("@pytest.mark.skip", "@pytest.mark.xfail", "pytest.skip(", "pytest.xfail("):
            if marker in lowered:
                violations.append(
                    LockViolationRecord(
                        code="SKIP_MARKER_INJECTED",
                        path=str(path),
                        detail=f"found {marker} in test file",
                        iteration=iteration,
                    )
                )
        return violations

    def check_density(
        self,
        content: str,
        path: Path,
        iteration: int,
    ) -> list[LockViolationRecord]:
        """Detect trivial assertions and assertions wrapped in pytest.raises."""
        violations: list[LockViolationRecord] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return violations

        self._set_parents(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                if isinstance(node.test, ast.Constant) and node.test.value is True:
                    violations.append(
                        LockViolationRecord(
                            code="TRIVIAL_ASSERTION",
                            path=str(path),
                            detail="assert True found",
                            iteration=iteration,
                        )
                    )
                if self._inside_raises(node):
                    violations.append(
                        LockViolationRecord(
                            code="RAISES_WRAP",
                            path=str(path),
                            detail="assertion wrapped in pytest.raises block",
                            iteration=iteration,
                        )
                    )

        function_assert_counts = self._function_assert_counts(tree)
        if function_assert_counts and all(c == 0 for c in function_assert_counts.values()):
            violations.append(
                LockViolationRecord(
                    code="ASSERTION_DENSITY_DROPPED",
                    path=str(path),
                    detail="no assert statements in any test function",
                    iteration=iteration,
                )
            )
        return violations

    @staticmethod
    def _set_parents(tree: ast.AST) -> None:
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                setattr(child, "parent", parent)

    @staticmethod
    def _inside_raises(node: ast.AST) -> bool:
        parent = getattr(node, "parent", None)
        while parent is not None:
            if isinstance(parent, ast.With):
                for item in parent.items:
                    ctx = item.context_expr
                    if isinstance(ctx, ast.Call):
                        func = ctx.func
                        if isinstance(func, ast.Attribute) and func.attr == "raises":
                            return True
                        if isinstance(func, ast.Name) and func.id == "raises":
                            return True
            parent = getattr(parent, "parent", None)
        return False

    @staticmethod
    def _function_assert_counts(tree: ast.AST) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
                if not name.startswith("test_"):
                    continue
                counts[name] = sum(
                    1 for child in ast.walk(node) if isinstance(child, ast.Assert)
                )
        return counts

    def check_write_path(
        self,
        rel_path: str,
        iteration: int,
    ) -> list[LockViolationRecord]:
        """Ensure a proposed write stays inside the workspace source or test
        tree and never targets the manifest or CI configuration.
        """
        violations: list[LockViolationRecord] = []
        lowered = rel_path.replace("\\", "/").lower()
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

        if self.workspace_dir is not None:
            abs_path = (self.workspace_dir / rel_path).resolve()
            if not abs_path.is_relative_to(self.workspace_dir.resolve()):
                violations.append(
                    LockViolationRecord(
                        code="WRITE_OUTSIDE_SRC",
                        path=rel_path,
                        detail="path escapes workspace directory",
                        iteration=iteration,
                    )
                )
        return violations
