from __future__ import annotations

import os
from pathlib import Path

from groundtruth.config import PROJECT_ROOT

SANDBOX_SENTINEL = ".groundtruth-sandbox"
ALLOWED_ROOT = PROJECT_ROOT.resolve()


class WorkspaceError(Exception):
    pass


def _home_path() -> Path:
    return Path.home().resolve()


def _is_ancestor_of(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_sandbox(sandbox_path: Path, workspace_id: str) -> None:
    resolved = sandbox_path.resolve()
    home = _home_path()

    if resolved == home:
        raise WorkspaceError(
            f"REFUSED: sandbox path resolves to home directory ({home}). "
            "This would stage private keys and credentials."
        )

    if _is_ancestor_of(resolved, home):
        raise WorkspaceError(
            f"REFUSED: sandbox path ({resolved}) is an ancestor of home ({home})."
        )

    if not _is_ancestor_of(ALLOWED_ROOT, resolved):
        raise WorkspaceError(
            f"REFUSED: sandbox path ({resolved}) is not under "
            f"allowed root ({ALLOWED_ROOT})."
        )

    sentinel = resolved / SANDBOX_SENTINEL
    if not sentinel.exists():
        raise WorkspaceError(
            f"REFUSED: sandbox sentinel file not found at {sentinel}. "
            f"Create {SANDBOX_SENTINEL} in the workspace root."
        )

    stored_id = sentinel.read_text(encoding="utf-8").strip()
    if stored_id != workspace_id:
        raise WorkspaceError(
            f"REFUSED: sentinel workspace id mismatch. "
            f"Expected '{workspace_id}', found '{stored_id}'."
        )


def ensure_sandbox(sandbox_path: Path, workspace_id: str) -> Path:
    resolved = sandbox_path.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    sentinel = resolved / SANDBOX_SENTINEL
    if not sentinel.exists():
        sentinel.write_text(workspace_id, encoding="utf-8", newline="\n")
    return resolved


def preflight_home_repo_check() -> list[str]:
    home = _home_path()
    git_dir = home / ".git"
    issues: list[str] = []
    if git_dir.exists():
        issues.append(
            f"WARNING: Home directory ({home}) appears to be a git repository. "
            f"A 'git add .' from an agent would stage private keys and credentials. "
            f"Consider removing the .git directory or adding a .gitignore."
        )
    return issues
