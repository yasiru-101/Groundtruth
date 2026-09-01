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
    "ls-remote",
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


def normalize_repo_slug(url: str) -> str:
    """Reduce any GitHub remote URL form to ``owner/name``."""
    url = url.strip()
    if not url:
        return ""
    url = url.removesuffix(".git")
    for prefix in ("https://github.com/", "git@github.com:", "ssh://git@github.com/"):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


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


def _flag_value(args: list[str], flag: str) -> Optional[str]:
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
    return None


def _positionals(args: list[str]) -> list[str]:
    return [a for a in args if not a.startswith("-")]


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

    def _validate_push_remote(self, args: list[str]) -> None:
        """Push may only target the allowlisted remote, by name or URL."""
        if not self.allowed_remote:
            return

        positionals = _positionals(args[2:])
        if positionals:
            target = positionals[0]
            if "/" in target or "://" in target:
                if normalize_repo_slug(target) != self.allowed_remote:
                    raise GitRefusal(
                        f"Refusing push to {target!r}: only {self.allowed_remote!r} is allowed.",
                        args,
                    )
                return
            remote_name = target
        else:
            remote_name = "origin"

        probe = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            cwd=str(self.sandbox_path),
            capture_output=True,
            text=True,
            shell=False,
        )
        url = probe.stdout.strip() if probe.returncode == 0 else ""
        if normalize_repo_slug(url) != self.allowed_remote:
            raise GitRefusal(
                f"Refusing push via remote {remote_name!r} ({url or 'unset'}): "
                f"only {self.allowed_remote!r} is allowed.",
                args,
            )

    def _validate_gh_target(self, args: list[str]) -> None:
        """gh commands must target the allowlisted repo when one is set."""
        if not self.allowed_remote:
            return

        sub = args[1] if len(args) > 1 else ""
        rest = args[2:]

        if sub in ("pr", "run"):
            slug = _flag_value(rest, "--repo")
            if slug is None:
                raise GitRefusal(
                    f"gh {sub} must pass --repo {self.allowed_remote} explicitly.",
                    args,
                )
            if slug != self.allowed_remote:
                raise GitRefusal(
                    f"gh {sub} targets {slug!r}: only {self.allowed_remote!r} is allowed.",
                    args,
                )
        elif sub == "repo":
            for verb in ("create", "delete"):
                if verb in rest and rest.index(verb) + 1 < len(rest):
                    slug = rest[rest.index(verb) + 1]
                    if slug != self.allowed_remote:
                        raise GitRefusal(
                            f"gh repo {verb} {slug!r}: only {self.allowed_remote!r} is allowed.",
                            args,
                        )
        elif sub == "api":
            repo_root = f"repos/{self.allowed_remote}"
            for arg in _positionals(rest):
                if arg.startswith("repos/") and not (
                    arg == repo_root or arg.startswith(repo_root + "/")
                ):
                    raise GitRefusal(
                        f"gh api {arg!r}: only repos/{self.allowed_remote}/ is allowed.",
                        args,
                    )

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
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        _validate_command(args)

        if _is_write_command(args):
            self._validate_sandbox()

        if len(args) > 1 and args[1] == "push":
            self._validate_push_remote(args)

        env = self._build_env() if _is_write_command(args) else os.environ.copy()
        if env_extra:
            env.update(env_extra)

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

        self._validate_gh_target(args)

        return subprocess.run(
            args,
            cwd=str(self.sandbox_path),
            capture_output=capture_output,
            text=True,
            shell=False,
            check=check,
        )
