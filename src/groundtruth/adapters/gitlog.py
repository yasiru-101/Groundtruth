"""Read-only git history adapter, behind the record/replay envelope.

All git invocations go through GitGuard.run (read commands never mutate the
repo). Output is parsed from a stable ``--format`` string with unit
separators so commit records survive round-tripping through fixtures.
"""

from __future__ import annotations

import subprocess
from typing import Any

from groundtruth.adapters.base import Envelope, RequestSpec

_SEP = "\x1f"  # unit separator between fields
_REC = "\x1e"  # record separator between commits
_FORMAT = f"%H{_SEP}%aI{_SEP}%cI{_SEP}%an{_SEP}%ae{_SEP}%s{_SEP}%P{_REC}"


class GitLogError(Exception):
    pass


def _parse_commits(raw: str) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    for record in raw.split(_REC):
        if not record.strip():
            continue
        fields = record.strip("\n").split(_SEP)
        if len(fields) != 7:
            raise GitLogError(
                f"Unexpected git log record (got {len(fields)} fields): {record[:120]!r}"
            )
        sha, author_date, commit_date, author_name, author_email, subject, parents = fields
        commits.append(
            {
                "sha": sha,
                "author_date": author_date,
                "commit_date": commit_date,
                "author_name": author_name,
                "author_email": author_email,
                "subject": subject,
                "parents": parents.split() if parents else [],
                "is_merge": len(parents.split()) > 1,
            }
        )
    return commits


class GitLog:
    def __init__(self, envelope: Envelope, guard: Any) -> None:
        self._envelope = envelope
        self._guard = guard

    def _git(self, args: list[str], *, params: dict[str, Any]) -> Any:
        spec = RequestSpec(method="GIT", url="git:log", params=params)

        def live() -> Any:
            try:
                result = self._guard.run(args)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()[:2000]
                raise GitLogError(
                    f"git {' '.join(args[:3])}... failed (exit {exc.returncode}): {stderr}"
                ) from exc
            return result.stdout or ""

        return self._envelope.call(spec, live)

    def commits(
        self,
        rev: str,
        *,
        base: str | None = None,
        merges_only: bool = False,
        max_count: int = 500,
    ) -> list[dict[str, Any]]:
        """Commits reachable from ``rev`` (optionally not from ``base``).

        Returns newest-first, one dict per commit, with author/commit dates
        and parent SHAs (more than one parent means a merge commit).
        """
        params: dict[str, Any] = {
            "rev": rev,
            "base": base,
            "merges_only": merges_only,
            "max_count": max_count,
        }
        args = ["git", "log", f"{base}..{rev}" if base else rev, f"-n{max_count}"]
        if merges_only:
            args.append("--merges")
        args.append(f"--format={_FORMAT}")
        return _parse_commits(self._git(args, params=params))

    def branches(self) -> list[str]:
        raw = self._git(
            ["git", "branch", "--format=%(refname:short)"],
            params={"kind": "branches"},
        )
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def commit(self, sha: str) -> dict[str, Any] | None:
        raw = self._git(
            ["git", "show", "-s", sha, f"--format={_FORMAT}"],
            params={"kind": "show", "sha": sha},
        )
        commits = _parse_commits(raw)
        return commits[0] if commits else None

    def tip_sha(self, rev: str = "HEAD") -> str | None:
        raw = self._git(
            ["git", "rev-parse", rev],
            params={"kind": "rev-parse", "rev": rev},
        )
        return raw.strip() or None

    def remote_url(self, name: str = "origin") -> str | None:
        raw = self._git(
            ["git", "remote", "get-url", name],
            params={"kind": "remote-url", "name": name},
        )
        return raw.strip() or None
