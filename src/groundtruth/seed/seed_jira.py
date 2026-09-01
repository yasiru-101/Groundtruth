"""Seed the Jira board from scenario.yaml.

Idempotency: every seeded ticket carries a unique ``gt-hint-<hint>`` label.
Before creating anything the seeder searches the project for the seed
label; a hint already present is reused, never duplicated — reruns create
zero issues. The seeder refuses to run against any project key other than
the scenario's configured demo key.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from groundtruth.adapters.jira import JiraClient, adf_text, adf_to_text
from groundtruth.config import Settings
from groundtruth.contracts.ledger import ApprovalRef, LedgerMode, LedgerOutcome
from groundtruth.ids import content_hash
from groundtruth.ledger.writer import LedgerWriter

SCENARIO_PATH = Path(__file__).parent / "scenario.yaml"


class SeedError(Exception):
    pass


def load_scenario(path: Path = SCENARIO_PATH) -> dict[str, Any]:
    scenario = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(scenario, dict):
        raise SeedError(f"Scenario {path} did not parse to a mapping.")
    for required in ("epoch", "jira", "git", "files", "commits", "tickets"):
        if required not in scenario:
            raise SeedError(f"Scenario {path} is missing required key {required!r}.")
    return scenario


def hint_label(hint: str) -> str:
    return f"gt-hint-{hint}"


class JiraSeeder:
    def __init__(
        self,
        settings: Settings,
        client: JiraClient,
        scenario: dict[str, Any],
        ledger: LedgerWriter | None = None,
    ) -> None:
        self._settings = settings
        self._client = client
        self._scenario = scenario
        self._ledger = ledger
        self._project_key = scenario["jira"]["project_key"]
        self._seed_label = scenario["jira"]["seed_label"]
        self._control_label = scenario["jira"]["control_label"]
        self._issue_type = scenario["jira"].get("issue_type", "Task")

    # -- reads -------------------------------------------------------------

    def existing_by_hint(self) -> dict[str, dict[str, Any]]:
        jql = f'project = "{self._project_key}" AND labels = "{self._seed_label}"'
        issues = self._client.search(jql, fields=["summary", "status", "labels"])
        by_hint: dict[str, dict[str, Any]] = {}
        for issue in issues:
            for label in issue.get("fields", {}).get("labels", []):
                if label.startswith("gt-hint-"):
                    by_hint[label[len("gt-hint-"):]] = issue
        return by_hint

    def plan(self) -> list[dict[str, Any]]:
        existing = self.existing_by_hint()
        return [t for t in self._scenario["tickets"] if t["hint"] not in existing]

    # -- writes ------------------------------------------------------------

    def _labels_for(self, ticket: dict[str, Any]) -> list[str]:
        labels = [self._seed_label, hint_label(ticket["hint"])]
        if ticket.get("points"):
            labels.append(f"gt-points-{ticket['points']}")
        for component in ticket.get("components", []):
            labels.append(f"gt-component-{component}")
        if ticket.get("control"):
            labels.append(self._control_label)
        return labels

    def _current_status(self, issue_key: str) -> str:
        issue = self._client.get_issue(issue_key, fields=["status"])
        return (issue.get("fields", {}).get("status") or {}).get("name", "")

    def _ledger_append(self, action: str, subject: str, *, outcome: LedgerOutcome = LedgerOutcome.OK,
                       error: str | None = None, approval: ApprovalRef | None = None,
                       inputs: str = "") -> None:
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

    def run(self, approval: ApprovalRef | None = None) -> list[dict[str, Any]]:
        """Create missing tickets, converge statuses, add comments once.

        Returns the manifest ticket list (keys resolved, branch specs attached).
        """
        existing = self.existing_by_hint()
        manifest_tickets: list[dict[str, Any]] = []

        for ticket in self._scenario["tickets"]:
            hint = ticket["hint"]
            issue = existing.get(hint)

            if issue is None:
                fields: dict[str, Any] = {
                    "project": {"key": self._project_key},
                    "summary": ticket["summary"],
                    "description": adf_text(ticket.get("description", "").strip()),
                    "issuetype": {"name": self._issue_type},
                    "labels": self._labels_for(ticket),
                }
                issue = self._client.create_issue(fields)
                self._ledger_append(
                    "seed.jira.create_issue",
                    issue["key"],
                    approval=approval,
                    inputs=content_hash(hint, ticket["summary"]),
                )

            key = issue["key"]
            target_status = ticket.get("status", "")
            current = self._current_status(key)
            if target_status and current != target_status:
                try:
                    self._client.transition_to(key, target_status)
                    self._ledger_append(
                        "seed.jira.transition",
                        key,
                        approval=approval,
                        inputs=content_hash(key, current, target_status),
                    )
                except Exception as exc:
                    self._ledger_append(
                        "seed.jira.transition",
                        key,
                        outcome=LedgerOutcome.ERROR,
                        error=str(exc),
                        approval=approval,
                    )
                    raise

            for comment_text in ticket.get("comments", []):
                if not self._comment_exists(key, comment_text):
                    self._client.add_comment(key, comment_text)
                    self._ledger_append(
                        "seed.jira.comment",
                        key,
                        approval=approval,
                        inputs=content_hash(key, comment_text),
                    )

            manifest_tickets.append(
                {
                    "hint": hint,
                    "key": key,
                    "summary": ticket["summary"],
                    "status": target_status or current,
                    "control": bool(ticket.get("control")),
                    "branch": ticket.get("branch"),
                }
            )

        return manifest_tickets

    def _comment_exists(self, issue_key: str, text: str) -> bool:
        for comment in self._client.get_comments(issue_key):
            body = comment.get("body") or {}
            if adf_to_text(body).strip() == text.strip():
                return True
        return False


def validate_against_settings(settings: Settings, scenario: dict[str, Any]) -> None:
    """The seeder only ever touches the configured demo project."""
    scenario_key = scenario["jira"]["project_key"]
    settings_key = settings.jira_project_key
    if not settings_key:
        raise SeedError(
            "JIRA_PROJECT_KEY is not configured. The seeder refuses to run "
            "without an explicit demo project key (set it in .env)."
        )
    if settings_key != scenario_key:
        raise SeedError(
            f"Refusing to seed: settings project key {settings_key!r} does not "
            f"match the scenario demo key {scenario_key!r}."
        )


def build_manifest(
    scenario: dict[str, Any],
    project_key: str,
    tickets: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    return {
        "scenario_version": scenario["scenario_version"],
        "project_key": project_key,
        "run_id": run_id,
        "seeded_at": datetime.now(timezone.utc).isoformat(),
        "tickets": tickets,
    }
