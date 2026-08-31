"""Tests for the safety guard: git_guard + workspace.

Every banned git form from the home directory must be refused.
The sandbox guard must be exercised through the real spaced path.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from groundtruth.config import PROJECT_ROOT
from groundtruth.safety.git_guard import GitGuard, GitRefusal, _validate_command
from groundtruth.safety.workspace import (
    SANDBOX_SENTINEL,
    WorkspaceError,
    ensure_sandbox,
    preflight_home_repo_check,
    validate_sandbox,
)


class TestBannedGitCommands:
    """Every banned git form must be refused by validation alone (no sandbox needed)."""

    @pytest.mark.parametrize(
        "args",
        [
            ["git", "add", "."],
            ["git", "add", "-A"],
            ["git", "add", "-u"],
            ["git", "add", "--all"],
            ["git", "add", "--update"],
            ["git", "commit", "-a", "-m", "sneaky"],
            ["git", "commit", "--all", "-m", "sneaky"],
            ["git", "push", "--force"],
            ["git", "push", "-f"],
            ["git", "push", "--force-with-lease"],
            ["git", "clean", "-fd"],
            ["git", "reset", "--hard"],
            ["git", "stash"],
            ["git", "filter-branch"],
            ["git", "rebase", "-i", "HEAD~3"],
        ],
    )
    def test_banned_commands_refused(self, args: list[str]) -> None:
        with pytest.raises(GitRefusal):
            _validate_command(args)

    def test_absolute_path_in_add_refused(self) -> None:
        with pytest.raises(GitRefusal, match="Absolute path"):
            _validate_command(["git", "add", "C:/Users/secret/key.pem"])

    def test_path_traversal_in_add_refused(self) -> None:
        with pytest.raises(GitRefusal, match="Path traversal"):
            _validate_command(["git", "add", "../../../etc/passwd"])

    def test_path_traversal_in_checkout_refused(self) -> None:
        with pytest.raises(GitRefusal, match="Path traversal"):
            _validate_command(["git", "checkout", "../../../etc/passwd"])

    def test_checkout_dot_refused(self) -> None:
        with pytest.raises(GitRefusal, match="checkout"):
            _validate_command(["git", "checkout", "."])

    def test_unknown_command_refused(self) -> None:
        with pytest.raises(GitRefusal, match="not in the allowlist"):
            _validate_command(["git", "bisect", "start"])

    def test_non_git_command_refused(self) -> None:
        with pytest.raises(GitRefusal, match="Only 'git'"):
            _validate_command(["rm", "-rf", "/"])

    def test_empty_command_refused(self) -> None:
        with pytest.raises(GitRefusal):
            _validate_command([])


class TestAllowedGitCommands:
    """These commands must pass validation."""

    @pytest.mark.parametrize(
        "args",
        [
            ["git", "init"],
            ["git", "checkout", "-b", "feature/AUTO-14"],
            ["git", "add", "src/main.py", "tests/test_main.py"],
            ["git", "commit", "-m", "initial commit"],
            ["git", "push"],
            ["git", "rev-parse", "--show-toplevel"],
            ["git", "log", "--oneline"],
            ["git", "status"],
            ["git", "diff"],
            ["git", "branch"],
            ["git", "show", "HEAD"],
            ["git", "remote", "-v"],
        ],
    )
    def test_allowed_commands_pass(self, args: list[str]) -> None:
        _validate_command(args)


class TestWorkspaceGuard:
    """Sandbox validation with the real spaced path."""

    def test_home_directory_refused(self) -> None:
        home = Path.home()
        workspace_id = str(uuid.uuid4())
        with pytest.raises(WorkspaceError, match="home directory"):
            validate_sandbox(home, workspace_id)

    def test_outside_allowed_root_refused(self, tmp_path: Path) -> None:
        workspace_id = str(uuid.uuid4())
        sentinel = tmp_path / SANDBOX_SENTINEL
        sentinel.write_text(workspace_id, encoding="utf-8")
        with pytest.raises(WorkspaceError, match="not under"):
            validate_sandbox(tmp_path, workspace_id)

    def test_missing_sentinel_refused(self) -> None:
        workspace_dir = PROJECT_ROOT / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        sentinel = workspace_dir / SANDBOX_SENTINEL
        sentinel.unlink(missing_ok=True)

        workspace_id = str(uuid.uuid4())
        with pytest.raises(WorkspaceError, match="sentinel"):
            validate_sandbox(workspace_dir, workspace_id)

    def test_sentinel_mismatch_refused(self) -> None:
        workspace_dir = PROJECT_ROOT / "workspace"
        workspace_id = str(uuid.uuid4())
        sentinel = workspace_dir / SANDBOX_SENTINEL
        sentinel.write_text("wrong-id", encoding="utf-8")

        with pytest.raises(WorkspaceError, match="mismatch"):
            validate_sandbox(workspace_dir, workspace_id)

        sentinel.unlink(missing_ok=True)

    def test_valid_sandbox_passes(self) -> None:
        workspace_id = str(uuid.uuid4())
        workspace_dir = PROJECT_ROOT / "workspace"
        ensure_sandbox(workspace_dir, workspace_id)
        validate_sandbox(workspace_dir, workspace_id)

    def test_ensure_sandbox_creates_sentinel(self) -> None:
        workspace_id = str(uuid.uuid4())
        workspace_dir = PROJECT_ROOT / "workspace"
        sentinel = workspace_dir / SANDBOX_SENTINEL
        sentinel.unlink(missing_ok=True)

        ensure_sandbox(workspace_dir, workspace_id)
        assert sentinel.exists()
        assert sentinel.read_text(encoding="utf-8") == workspace_id

    def test_spaced_path_works(self) -> None:
        """The project path contains a space. Sandbox must work through it."""
        assert " " in str(PROJECT_ROOT)
        workspace_id = str(uuid.uuid4())
        workspace_dir = PROJECT_ROOT / "workspace"
        sentinel = workspace_dir / SANDBOX_SENTINEL
        sentinel.unlink(missing_ok=True)
        ensure_sandbox(workspace_dir, workspace_id)
        validate_sandbox(workspace_dir, workspace_id)


class TestGitGuardFromHome:
    """GitGuard pointed at the home directory must refuse writes."""

    def test_guard_refuses_home_sandbox(self) -> None:
        home = Path.home()
        guard = GitGuard(sandbox_path=home, workspace_id="test")
        with pytest.raises(GitRefusal):
            guard.run(["git", "add", "."])

    def test_guard_refuses_banned_commands_at_home(self) -> None:
        home = Path.home()
        guard = GitGuard(sandbox_path=home, workspace_id="test")

        banned = [
            ["git", "add", "."],
            ["git", "add", "-A"],
            ["git", "commit", "-a", "-m", "sneaky"],
            ["git", "push", "--force"],
            ["git", "clean", "-fd"],
            ["git", "reset", "--hard"],
        ]
        for cmd in banned:
            with pytest.raises(GitRefusal):
                guard.run(cmd)


class TestPreflight:
    def test_preflight_runs_without_error(self) -> None:
        issues = preflight_home_repo_check()
        assert isinstance(issues, list)
