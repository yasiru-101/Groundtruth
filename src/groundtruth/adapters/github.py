"""GitHub adapter: gh CLI wrapper behind the record/replay envelope.

Every gh invocation goes through GitGuard.run_gh (arg lists, shell=False) —
this module never calls subprocess itself, per the single-choke-point rule.
When the guard is pinned to a repo slug, every ``gh pr``/``gh run`` call
must pass ``--repo <slug>`` and ``gh api`` may only touch that repo, so a
runaway command cannot reach another repository.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from groundtruth.adapters.base import Envelope, RequestSpec
from groundtruth.config import RunMode, Settings
from groundtruth.safety.git_guard import GitGuard


class GitHubError(Exception):
    pass


PR_LIST_FIELDS = (
    "number,title,state,headRefName,baseRefName,author,createdAt,mergedAt,"
    "mergeCommit,url"
)
PR_VIEW_FIELDS = (
    "number,title,state,headRefName,baseRefName,author,createdAt,mergedAt,"
    "mergedBy,url,body,files,commits,reviews"
)


class GitHubClient:
    def __init__(self, settings: Settings, envelope: Envelope, guard: GitGuard) -> None:
        self._settings = settings
        self._envelope = envelope
        self._guard = guard

        if envelope.mode is not RunMode.REPLAY:
            missing = [
                name
                for name, value in [
                    ("GITHUB_REPO_OWNER", settings.github_repo_owner),
                    ("GITHUB_REPO_NAME", settings.github_repo_name),
                ]
                if not value
            ]
            if missing:
                raise GitHubError(
                    f"GitHub adapter in {envelope.mode.value} mode requires: "
                    f"{', '.join(missing)} (set in .env)"
                )

        self.slug = f"{settings.github_repo_owner}/{settings.github_repo_name}"
        if guard.allowed_remote and guard.allowed_remote != self.slug:
            raise GitHubError(
                f"GitGuard is pinned to {guard.allowed_remote!r} but settings "
                f"describe {self.slug!r}."
            )

    # -- envelope plumbing -------------------------------------------------

    def _gh(self, args: list[str], *, parse_json: bool = False) -> Any:
        spec = RequestSpec(method="GH", url="gh:cli", params={"args": args})

        def live() -> Any:
            try:
                result = self._guard.run_gh(args)
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or "").strip()[:2000]
                raise GitHubError(
                    f"gh {' '.join(args[:4])}... failed "
                    f"(exit {exc.returncode}): {stderr}"
                ) from exc
            stdout = result.stdout or ""
            if parse_json:
                if not stdout.strip():
                    return None
                try:
                    return json.loads(stdout)
                except json.JSONDecodeError as exc:
                    raise GitHubError(
                        f"gh {' '.join(args[:4])}... returned non-JSON output: "
                        f"{stdout[:500]!r}"
                    ) from exc
            return stdout.strip()

        return self._envelope.call(spec, live)

    # -- reads -------------------------------------------------------------

    def pr_list(self, state: str = "all", limit: int = 100) -> list[dict[str, Any]]:
        return self._gh(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                self.slug,
                "--state",
                state,
                "--limit",
                str(limit),
                "--json",
                PR_LIST_FIELDS,
            ],
            parse_json=True,
        )

    def pr_view(self, number: int) -> dict[str, Any]:
        return self._gh(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                self.slug,
                "--json",
                PR_VIEW_FIELDS,
            ],
            parse_json=True,
        )

    def check_runs(self, ref: str) -> dict[str, Any]:
        """Check runs for a commit ref, via the REST endpoint gh api exposes."""
        return self._gh(
            [
                "gh",
                "api",
                f"repos/{self.slug}/commits/{ref}/check-runs",
                "--method",
                "GET",
                "-f",
                "per_page=100",
            ],
            parse_json=True,
        )

    # -- writes ------------------------------------------------------------

    def pr_create(
        self,
        title: str,
        body: str | None = None,
        head: str | None = None,
        base: str = "main",
        *,
        draft: bool = False,
        body_file: Path | str | None = None,
    ) -> str:
        """Create a PR; returns its URL."""
        args = [
            "gh",
            "pr",
            "create",
            "--repo",
            self.slug,
            "--title",
            title,
        ]
        if body_file is not None:
            args.extend(["--body-file", str(Path(body_file).resolve())])
        elif body is not None:
            args.extend(["--body", body])
        if head is not None:
            args.extend(["--head", head])
        args.extend(["--base", base])
        if draft:
            args.append("--draft")
        return self._gh(args)

    def pr_merge(self, number: int, method: str = "merge") -> str:
        if method not in ("merge", "squash", "rebase"):
            raise GitHubError(f"Unsupported merge method: {method!r}")
        return self._gh(
            [
                "gh",
                "pr",
                "merge",
                str(number),
                "--repo",
                self.slug,
                f"--{method}",
            ]
        )

    def repo_create(self, private: bool = False) -> str:
        return self._gh(
            [
                "gh",
                "repo",
                "create",
                self.slug,
                "--public" if not private else "--private",
            ]
        )

    def repo_get(self) -> dict[str, Any] | None:
        """Fetch repo metadata; None when the repo does not exist."""
        try:
            result = self._gh(["gh", "api", f"repos/{self.slug}"], parse_json=True)
        except GitHubError as exc:
            if "Not Found" in str(exc):
                return None
            raise
        return result if isinstance(result, dict) else None

    def repo_set_description(self, description: str) -> None:
        self._gh(
            [
                "gh",
                "api",
                f"repos/{self.slug}",
                "--method",
                "PATCH",
                "-f",
                f"description={description}",
            ]
        )

    def repo_delete(self) -> None:
        self._gh(["gh", "repo", "delete", self.slug, "--yes"])
