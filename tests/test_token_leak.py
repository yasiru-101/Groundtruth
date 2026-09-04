"""Ensure stored tokens never leak through API responses or error messages."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import create_app
from groundtruth.api.settings import ApiSettings
from groundtruth.connections.store import ConnectionStore
from groundtruth.safety.redact import redact_values


@pytest.fixture
def leak_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GT_SECRET_KEY", "m7RGYJ8vCR2xWgS3_KzR3yNqLEpT6uVvZ7wX9yZ0abc=")
    connections_path = tmp_path / "connections.json"
    monkeypatch.setenv("GT_CONNECTIONS_PATH", str(connections_path))
    settings = ApiSettings()
    store = ConnectionStore(connections_path)
    store.set_github(
        auth_kind="pat",
        repo_owner="acme",
        repo_name="corp",
        token="ghp_supersecrettoken1234567890abcdefghijklmnopqrstuvwxyz",
        login="demo",
        scopes=["repo"],
    )
    store.set_jira(
        auth_kind="basic",
        site_url="https://acme.atlassian.net",
        project_key="GT",
        email="demo@example.com",
        api_token="ATATT3xFfGF0abcdefghijklmnopqrstuvwxyz1234",
    )
    store.set_llm(
        provider="OpenAI",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key="sk-live-abcdefghijklmnop1234567890",
    )
    return TestClient(create_app(settings))


def test_connections_status_does_not_expose_tokens(leak_client: TestClient) -> None:
    r = leak_client.get("/api/connections")
    assert r.status_code == 200
    text = r.text
    assert "ghp_supersecrettoken" not in text
    assert "ATATT3xFfGF0" not in text
    assert "sk-live-abcdefghijklmnop" not in text
    assert r.json()["github"]["connected"] is True
    assert r.json()["jira"]["connected"] is True
    assert r.json()["llm"]["connected"] is True


def test_parse_url_does_not_expose_tokens(leak_client: TestClient) -> None:
    r = leak_client.post(
        "/api/connections/parse-url",
        json={"url": "https://github.com/acme/corp/pull/123"},
    )
    assert r.status_code == 200
    assert "ghp_" not in r.text


def test_redact_values_scrubs_exact_secrets() -> None:
    secrets = ["ghp_supersecrettoken", "ATATT3xFfGF0", "sk-live-abc"]
    text = "Error: ghp_supersecrettoken and ATATT3xFfGF0 plus sk-live-abc leaked"
    result = redact_values(text, secrets)
    for secret in secrets:
        assert secret not in result
    assert result.count("[REDACTED]") == 3
