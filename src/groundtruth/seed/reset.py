"""Tear down the synthetic board: Jira issues, the GitHub demo repo, the sandbox.

Safety rails:
- Jira deletion is scoped to the scenario project key AND the seed label, and
  the settings project key must match the scenario key (same refusal as the
  seeder).
- The GitHub repo is only deleted when its description carries the seeder's
  marker, proving Groundtruth created it. A repo that exists without the
  marker is reported and left alone.
- The local wipe only runs inside a validated sandbox (sentinel + workspace
  id match) and preserves the sentinel file itself.
"""

from __future__ import annotations

import os
import shutil
import stat
from typing import Any

from groundtruth.adapters.github import GitHubClient, GitHubError
from groundtruth.adapters.jira import JiraClient
from groundtruth.config import Settings
from groundtruth.contracts.ledger import ApprovalRef, LedgerMode, LedgerOutcome
from groundtruth.ids import content_hash
from groundtruth.ledger.writer import LedgerWriter
from groundtruth.safety.git_guard import GitGuard
from groundtruth.safety.workspace import SANDBOX_SENTINEL, validate_sandbox
from groundtruth.seed.seed_git import REPO_MARKER_DESCRIPTION
from groundtruth.seed.seed_jira import SeedError, validate_against_settings


def _force_rmtree(path: Any) -> None:
    """rmtree that clears the read-only bit git sets on .git objects (Windows)."""
    if path.is_dir():
        for child in path.rglob("*"):
            if child.is_file():
                os.chmod(child, stat.S_IWRITE)
        shutil.rmtree(path)
    elif path.exists():
        os.chmod(path, stat.S_IWRITE)
        path.unlink()


class Resetter:
    def __init__(
        self,
        settings: Settings,
        jira_client: JiraClient,
        guard: GitGuard,
        scenario: dict[str, Any],
        ledger: LedgerWriter | None = None,
        github: GitHubClient | None = None,
    ) -> None:
        self._settings = settings
        self._jira = jira_client
        self._guard = guard
        self._scenario = scenario
        self._ledger = ledger
        self._github = github
        self._sandbox = guard.sandbox_path
        self._project_key = scenario["jira"]["project_key"]
        self._seed_label = scenario["jira"]["seed_label"]

    # -- ledger ---------------------------------------------------------------

    def _ledger_append(
        self,
        action: str,
        subject: str,
        *,
        outcome: LedgerOutcome = LedgerOutcome.OK,
        error: str | None = None,
        approval: ApprovalRef | None = None,
        inputs: str = "",
    ) -> None:
        if self._ledger is None:
            return
        self._ledger.append(
            actor="seeder",
            action=action,
            mode=LedgerMode.APPLY,
            subject=subject,
            inputs_hash=inputs,
            outcome=outcome,
            error=error,
            approval=approval,
        )

    # -- reads ----------------------------------------------------------------

    def seeded_issues(self) -> list[dict[str, Any]]:
        jql = f'project = "{self._project_key}" AND labels = "{self._seed_label}"'
        return self._jira.search(jql, fields=["summary"])

    def repo_state(self) -> str:
        """One of: absent, ours, foreign."""
        if self._github is None:
            return "absent"
        try:
            repo = self._github.repo_get()
        except GitHubError:
            return "unknown"
        if repo is None:
            return "absent"
        return "ours" if repo.get("description") == REPO_MARKER_DESCRIPTION else "foreign"

    def plan(self) -> dict[str, Any]:
        return {
            "jira_issues": [
                {"key": issue["key"], "summary": issue["fields"].get("summary", "")}
                for issue in self.seeded_issues()
            ],
            "github_repo": self.repo_state(),
            "local_repo": (self._sandbox / ".git").exists(),
        }

    # -- writes -----------------------------------------------------------------

    def _delete_jira_issues(self, approval: ApprovalRef | None) -> list[str]:
        deleted: list[str] = []
        for issue in self.seeded_issues():
            key = issue["key"]
            try:
                self._jira.delete_issue(key)
            except Exception as exc:
                self._ledger_append(
                    "reset.jira.delete_issue",
                    key,
                    outcome=LedgerOutcome.ERROR,
                    error=str(exc),
                    approval=approval,
                    inputs=content_hash(key),
                )
                raise
            self._ledger_append(
                "reset.jira.delete_issue",
                key,
                approval=approval,
                inputs=content_hash(key),
            )
            deleted.append(key)
        return deleted

    def _delete_github_repo(self, approval: ApprovalRef | None) -> str:
        state = self.repo_state()
        if state == "absent":
            return "absent"
        if state != "ours":
            self._ledger_append(
                "reset.github.repo_delete",
                self._github.slug,
                outcome=LedgerOutcome.REFUSED,
                error=f"repo description does not carry the seed marker; refusing",
                approval=approval,
                inputs=content_hash(self._github.slug),
            )
            return state
        try:
            self._github.repo_delete()
        except GitHubError as exc:
            hint = str(exc)
            if "delete_repo" in hint:
                hint += " (the gh token needs the delete_repo scope: " \
                        "gh auth refresh -h github.com -s delete_repo)"
            self._ledger_append(
                "reset.github.repo_delete",
                self._github.slug,
                outcome=LedgerOutcome.ERROR,
                error=hint,
                approval=approval,
                inputs=content_hash(self._github.slug),
            )
            raise SeedError(hint) from exc
        self._ledger_append(
            "reset.github.repo_delete",
            self._github.slug,
            approval=approval,
            inputs=content_hash(self._github.slug),
        )
        return "deleted"

    def _wipe_local_sandbox(self) -> int:
        validate_sandbox(self._sandbox, self._guard.workspace_id)
        removed = 0
        for entry in self._sandbox.iterdir():
            if entry.name == SANDBOX_SENTINEL:
                continue
            _force_rmtree(entry)
            removed += 1
        return removed

    def run(self, approval: ApprovalRef | None = None) -> dict[str, Any]:
        validate_against_settings(self._settings, self._scenario)

        result: dict[str, Any] = {
            "jira_deleted": [],
            "github_repo": "skipped",
            "local_entries_removed": 0,
        }
        errors: list[str] = []

        try:
            result["jira_deleted"] = self._delete_jira_issues(approval)
        except Exception as exc:
            errors.append(f"jira: {exc}")

        if self._github is not None:
            try:
                result["github_repo"] = self._delete_github_repo(approval)
            except Exception as exc:
                errors.append(f"github: {exc}")

        try:
            result["local_entries_removed"] = self._wipe_local_sandbox()
        except Exception as exc:
            errors.append(f"local: {exc}")

        if errors:
            raise SeedError("Reset completed with errors: " + "; ".join(errors))
        return result
