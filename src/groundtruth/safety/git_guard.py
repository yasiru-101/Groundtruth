from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from groundtruth.config import PROJECT_ROOT

from .workspace import WorkspaceError, validate_sandbox

ALLOWED_COMMANDS = {
    "init",
    "checkout",
    "add",
    "commit",
    "push",
    "rev-parse",
    "log",
    "status",
    "diff",
    "branch",
    "show",
    "remote",
}

BANNED_ADD_PATHSPECS = {".", "-A", "-u", "--all", "--update"}

BANNED_COMMIT_FLAGS = {"-a", "--all"}

BANNED_PUSH_FLAGS = {"--force", "-f", "--force-with-lease"}

BANNED_COMMANDS = {
    "clean",
    "reset",
    "stash",
    "filter-branch",
    "rebase",
    "merge",
    "cherry-pick",
}

ALLOWED_GH_COMMANDS = {
    "pr",
    "repo",
    "api",
    "run",
}


class GitGuardError(Exception):
    pass


class GitRefusal(Exception):
    def __init__(self, reason: str, command: list[str]) -> None:
        self.reason = reason
        self.command = command
        super().__init__(f"REFUSED: {reason}")


def _validate_add_args(args: list[str]) -> None:
    for arg in args:
        if arg.startswith("-"):
            if arg in BANNED_ADD_PATHSPECS:
                raise GitRefusal(
                    f"'git add {arg}' is banned. Use explicit file paths.",
                    ["git", "add", arg],
                )
        elif arg == ".":
            raise GitRefusal(
                "'git add .' is banned. Use explicit file paths.",
                ["git", "add", "."],
            )
        elif os.path.isabs(arg):
            raise GitRefusal(
                f"Absolute path in git add is banned: {arg}",
                ["git", "add", arg],
            )
        elif ".." in arg:
            raise GitRefusal(
                f"Path traversal in git add is banned: {arg}",
                ["git", "add", arg],
            )


def _validate_commit_args(args: list[str]) -> None:
    for arg in args:
        if arg in BANNED_COMMIT_FLAGS:
            raise GitRefusal(
                f"'git commit {arg}' is banned. Stage files explicitly.",
                ["git", "commit", arg],
            )


def _validate_push_args(args: list[str]) -> None:
    for arg in args:
        if arg in BANNED_PUSH_FLAGS:
            raise GitRefusal(
                f"'git push {arg}' is banned.",
                ["git", "push", arg],
            )


def _validate_checkout_args(args: list[str]) -> None:
    if len(args) >= 2 and args[0] == "-b":
        return
    if args and args[0] == ".":
        raise GitRefusal(
            "'git checkout .' is banned.",
            ["git", "checkout", "."],
        )
    for arg in args:
        if ".." in arg:
            raise GitRefusal(
                f"Path traversal in git checkout is banned: {arg}",
                ["git", "checkout", arg],
            )


def _validate_command(args: list[str]) -> None:
    if not args or args[0] != "git":
        raise GitRefusal("Only 'git' commands are allowed.", args)

    git_args = args[1:]
    if not git_args:
        raise GitRefusal("Empty git command.", args)

    cmd = git_args[0]

    if cmd in BANNED_COMMANDS:
        raise GitRefusal(f"'git {cmd}' is banned entirely.", args)

    if cmd not in ALLOWED_COMMANDS:
        raise GitRefusal(f"'git {cmd}' is not in the allowlist.", args)

    sub_args = git_args[1:]

    if cmd == "add":
        _validate_add_args(sub_args)
    elif cmd == "commit":
        _validate_commit_args(sub_args)
    elif cmd == "push":
        _validate_push_args(sub_args)
    elif cmd == "checkout":
        _validate_checkout_args(sub_args)


def _is_write_command(args: list[str]) -> bool:
    if len(args) < 2:
        return False
    write_cmds = {"init", "add", "commit", "push", "checkout"}
    return args[1] in write_cmds


class GitGuard:
    def __init__(
        self,
        sandbox_path: Path,
        workspace_id: str,
        allowed_remote: str = "",
    ) -> None:
        self.sandbox_path = sandbox_path.resolve()
        self.workspace_id = workspace_id
        self.allowed_remote = allowed_remote

    def _validate_sandbox(self) -> None:
        validate_sandbox(self.sandbox_path, self.workspace_id)

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        git_dir = self.sandbox_path / ".git"
        env["GIT_DIR"] = str(git_dir)
        env["GIT_WORK_TREE"] = str(self.sandbox_path)
        return env

    def run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        _validate_command(args)

        if _is_write_command(args):
            self._validate_sandbox()

        env = self._build_env() if _is_write_command(args) else os.environ.copy()

        return subprocess.run(
            args,
            cwd=str(self.sandbox_path),
            env=env,
            capture_output=capture_output,
            text=True,
            shell=False,
            check=check,
        )

    def run_gh(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if not args or args[0] != "gh":
            raise GitRefusal("Only 'gh' commands are allowed.", args)

        gh_sub = args[1] if len(args) > 1 else ""
        if gh_sub not in ALLOWED_GH_COMMANDS:
            raise GitRefusal(f"'gh {gh_sub}' is not in the allowlist.", args)

        return subprocess.run(
            args,
            cwd=str(self.sandbox_path),
            capture_output=capture_output,
            text=True,
            shell=False,
            check=check,
        )
