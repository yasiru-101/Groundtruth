"""Jira Cloud REST v3 adapter, behind the record/replay envelope.

Uses the current ``/rest/api/3/search/jql`` endpoint (the old ``/search`` is
deprecated and drops ``total``), paginating via ``nextPageToken`` to
completion. Transitions are resolved by target status name against the
issue's actual workflow; an unresolvable name fails with the list of
available options rather than a bare error.
"""

from __future__ import annotations

from typing import Any

import httpx

from groundtruth.adapters.base import Envelope, RequestSpec
from groundtruth.config import RunMode, Settings
from groundtruth.safety.redact import redact


class JiraError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def adf_text(text: str) -> dict[str, Any]:
    """Minimal Atlassian Document Format doc holding one paragraph of text."""
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def adf_to_text(doc: Any) -> str:
    """Flatten an ADF doc back to plain text (for idempotency checks)."""
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "text" and isinstance(node.get("text"), str):
                parts.append(node["text"])
            for child in node.get("content") or []:
                walk(child)

    walk(doc)
    return "".join(parts)


SEARCH_PAGE_SIZE = 100
MAX_SEARCH_PAGES = 100


class JiraClient:
    def __init__(
        self,
        settings: Settings,
        envelope: Envelope,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._envelope = envelope

        if envelope.mode is not RunMode.REPLAY:
            if settings.jira_auth_mode == "oauth":
                missing = [
                    name
                    for name, value in [
                        ("JIRA_CLOUD_ID", settings.jira_cloud_id),
                        ("JIRA_ACCESS_TOKEN", settings.jira_access_token),
                    ]
                    if not value
                ]
            else:
                missing = [
                    name
                    for name, value in [
                        ("JIRA_BASE_URL", settings.jira_base_url),
                        ("JIRA_EMAIL", settings.jira_email),
                        ("JIRA_API_TOKEN", settings.jira_api_token),
                    ]
                    if not value
                ]
            if missing:
                raise JiraError(
                    f"Jira adapter in {envelope.mode.value} mode requires: "
                    f"{', '.join(missing)} (set in .env or connect in Settings)"
                )

        if settings.jira_auth_mode == "oauth":
            self._client = client or httpx.Client(
                base_url=f"https://api.atlassian.com/ex/jira/{settings.jira_cloud_id}",
                headers={
                    "Authorization": f"Bearer {settings.jira_access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        else:
            self._client = client or httpx.Client(
                base_url=settings.jira_base_url.rstrip("/"),
                auth=(settings.jira_email, settings.jira_api_token),
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=30.0,
            )

    def close(self) -> None:
        self._client.close()

    # -- envelope plumbing -------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        spec = RequestSpec(method=method, url=path, params=params, body=json_body)

        def live() -> Any:
            response = self._client.request(method, path, params=params, json=json_body)
            if response.status_code >= 400:
                raise JiraError(
                    f"Jira {method} {path} failed: HTTP {response.status_code}",
                    status_code=response.status_code,
                    body=redact(response.text[:2000]),
                )
            if response.status_code == 204 or not response.content:
                return None
            return response.json()

        return self._envelope.call(spec, live)

    # -- reads -------------------------------------------------------------

    def search(self, jql: str, fields: list[str] | None = None) -> list[dict[str, Any]]:
        """Run JQL, paginating through /search/jql until exhausted."""
        body: dict[str, Any] = {
            "jql": jql,
            "fields": fields or ["summary", "status"],
            "maxResults": SEARCH_PAGE_SIZE,
        }
        issues: list[dict[str, Any]] = []
        for _ in range(MAX_SEARCH_PAGES):
            page = self._request("POST", "/rest/api/3/search/jql", json_body=body)
            issues.extend(page.get("issues", []))
            token = page.get("nextPageToken")
            if not token:
                return issues
            body["nextPageToken"] = token
        raise JiraError(
            f"Search exceeded {MAX_SEARCH_PAGES} pages for JQL: {jql!r}"
        )

    def get_issue(self, issue_key: str, fields: list[str] | None = None) -> dict[str, Any]:
        params = {"fields": ",".join(fields)} if fields else None
        return self._request("GET", f"/rest/api/3/issue/{issue_key}", params=params)

    def get_changelog(self, issue_key: str) -> list[dict[str, Any]]:
        """All changelog entries, paginating via startAt/total."""
        values: list[dict[str, Any]] = []
        start_at = 0
        for _ in range(MAX_SEARCH_PAGES):
            page = self._request(
                "GET",
                f"/rest/api/3/issue/{issue_key}/changelog",
                params={"startAt": start_at, "maxResults": SEARCH_PAGE_SIZE},
            )
            batch = page.get("values", [])
            values.extend(batch)
            total = page.get("total", start_at + len(batch))
            start_at += len(batch)
            if start_at >= total:
                return values
        raise JiraError(f"Changelog for {issue_key} exceeded {MAX_SEARCH_PAGES} pages")

    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        response = self._request("GET", f"/rest/api/3/issue/{issue_key}/transitions")
        return response.get("transitions", [])

    def get_comments(self, issue_key: str) -> list[dict[str, Any]]:
        response = self._request("GET", f"/rest/api/3/issue/{issue_key}/comment")
        return response.get("comments", [])

    # -- writes ------------------------------------------------------------

    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/rest/api/3/issue", json_body={"fields": fields})

    def add_comment(self, issue_key: str, text: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/comment",
            json_body={"body": adf_text(text)},
        )

    def transition_to(self, issue_key: str, target_status: str) -> dict[str, Any]:
        """Transition by workflow-agnostic status name.

        Resolves the issue's actual transition id first; if the target status
        is not reachable, fails listing what is available.
        """
        transitions = self.get_transitions(issue_key)
        wanted = target_status.strip().lower()
        for transition in transitions:
            to_name = (transition.get("to") or {}).get("name", "")
            if to_name.strip().lower() == wanted or transition.get("name", "").strip().lower() == wanted:
                return self._apply_transition(issue_key, transition["id"])
        available = ", ".join(
            f"{t.get('name')!r}->{(t.get('to') or {}).get('name', '?')!r}" for t in transitions
        )
        raise JiraError(
            f"No transition on {issue_key} leads to status {target_status!r}. "
            f"Available: {available}"
        )

    def _apply_transition(self, issue_key: str, transition_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/rest/api/3/issue/{issue_key}/transitions",
            json_body={"transition": {"id": transition_id}},
        )

    def delete_issue(self, issue_key: str) -> None:
        self._request("DELETE", f"/rest/api/3/issue/{issue_key}")
