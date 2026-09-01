"""Jira search pagination to completion, against a mock transport.

The old /search endpoint dropped ``total``; /search/jql only signals
exhaustion via ``nextPageToken``, so the client must keep requesting pages
until the token disappears — and must send the token back on the next call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from groundtruth.adapters import jira as jira_module
from groundtruth.adapters.base import Envelope, FixtureStore
from groundtruth.adapters.jira import JiraClient, JiraError
from groundtruth.config import RunMode, Settings


Handler = Callable[[httpx.Request], httpx.Response]


def make_client(
    handler: Handler, tmp_path: Path
) -> tuple[JiraClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    http = httpx.Client(
        base_url="https://jira.example",
        transport=httpx.MockTransport(wrapped),
    )
    settings = Settings(
        jira_base_url="https://jira.example",
        jira_email="t@example.com",
        jira_api_token="tok",
    )
    envelope = Envelope(mode=RunMode.LIVE, store=FixtureStore(tmp_path))
    return JiraClient(settings, envelope, client=http), requests


def issue(key: str) -> dict[str, Any]:
    return {"key": key, "fields": {"summary": f"ticket {key}"}}


class TestSearchPagination:
    def test_paginates_to_completion_and_sends_token_back(
        self, tmp_path: Path
    ) -> None:
        issues = [issue(f"AUTO-{i}") for i in range(1, 6)]

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if "nextPageToken" not in body:
                return httpx.Response(
                    200, json={"issues": issues[:2], "nextPageToken": "page-2"}
                )
            assert body["nextPageToken"] == "page-2"
            return httpx.Response(200, json={"issues": issues[2:]})

        client, requests = make_client(handler, tmp_path)
        result = client.search("project = AUTO", fields=["summary"])

        assert [i["key"] for i in result] == [f"AUTO-{i}" for i in range(1, 6)]
        assert len(requests) == 2
        assert json.loads(requests[1].content)["nextPageToken"] == "page-2"
        assert json.loads(requests[0].content)["maxResults"] == jira_module.SEARCH_PAGE_SIZE

    def test_single_page_without_token_terminates(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"issues": [issue("AUTO-1")]})

        client, requests = make_client(handler, tmp_path)
        assert client.search("project = AUTO") == [issue("AUTO-1")]
        assert len(requests) == 1

    def test_runaway_pagination_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(jira_module, "MAX_SEARCH_PAGES", 3)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"issues": [issue("AUTO-1")], "nextPageToken": "forever"}
            )

        client, _ = make_client(handler, tmp_path)
        with pytest.raises(JiraError, match="exceeded 3 pages"):
            client.search("project = AUTO")


class TestChangelogPagination:
    def test_paginates_via_start_at_until_total(self, tmp_path: Path) -> None:
        entries = [{"id": str(i)} for i in range(5)]

        def handler(request: httpx.Request) -> httpx.Response:
            start_at = int(request.url.params["startAt"])
            batch = entries[start_at : start_at + 2]
            return httpx.Response(
                200, json={"values": batch, "total": len(entries)}
            )

        client, requests = make_client(handler, tmp_path)
        result = client.get_changelog("AUTO-1")

        assert result == entries
        assert [r.url.params["startAt"] for r in requests] == ["0", "2", "4"]


class TestTransitions:
    def test_resolves_transition_by_target_status_name(
        self, tmp_path: Path
    ) -> None:
        applied: list[dict[str, Any]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/transitions") and request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "transitions": [
                            {
                                "id": "31",
                                "name": "Finish Work",
                                "to": {"name": "Done"},
                            }
                        ]
                    },
                )
            applied.append(json.loads(request.content))
            return httpx.Response(204)

        client, _ = make_client(handler, tmp_path)
        client.transition_to("AUTO-1", "done")
        assert applied == [{"transition": {"id": "31"}}]

    def test_unresolvable_status_lists_available_transitions(
        self, tmp_path: Path
    ) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "transitions": [
                        {"id": "11", "name": "Start", "to": {"name": "In Progress"}},
                        {"id": "31", "name": "Finish", "to": {"name": "Done"}},
                    ]
                },
            )

        client, _ = make_client(handler, tmp_path)
        with pytest.raises(JiraError) as excinfo:
            client.transition_to("AUTO-1", "Blocked")
        message = str(excinfo.value)
        assert "Blocked" in message
        assert "'Start'->'In Progress'" in message
        assert "'Finish'->'Done'" in message


class TestErrorSurfacing:
    def test_http_error_raises_jira_error_with_body(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"errorMessages": ["bad JQL"], "warningMessages": []}
            )

        client, _ = make_client(handler, tmp_path)
        with pytest.raises(JiraError) as excinfo:
            client.search("nonsense")
        assert excinfo.value.status_code == 400
        assert "bad JQL" in excinfo.value.body

    def test_delete_issue_accepts_204(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(204)

        client, _ = make_client(handler, tmp_path)
        assert client.delete_issue("AUTO-1") is None
