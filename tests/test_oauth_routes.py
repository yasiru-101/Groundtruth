"""Tests for OAuth state handling and auth endpoints."""

from __future__ import annotations

import time
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import create_app
from groundtruth.api.oauth import OAuthStateStore, _pkce_challenge
from groundtruth.api.settings import ApiSettings


class TestOAuthStateStore:
    def test_single_use_state(self) -> None:
        store = OAuthStateStore()
        state, _, _ = store.issue()
        assert store.consume(state)[0] is True
        assert store.consume(state)[0] is False

    def test_expired_state_is_rejected(self) -> None:
        store = OAuthStateStore(ttl_seconds=-1)
        state, _, _ = store.issue()
        assert store.consume(state)[0] is False

    def test_pkce_challenge_matches_verifier(self) -> None:
        store = OAuthStateStore()
        state, challenge, verifier = store.issue(use_pkce=True)
        assert state
        assert verifier
        assert challenge == _pkce_challenge(verifier)
        ok, consumed_verifier = store.consume(state)
        assert ok is True
        assert consumed_verifier == verifier


@pytest.fixture
def configured_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GT_GITHUB_CLIENT_ID", "gh_client_id")
    monkeypatch.setenv("GT_GITHUB_CLIENT_SECRET", "gh_client_secret")
    monkeypatch.setenv("GT_JIRA_CLIENT_ID", "jira_client_id")
    monkeypatch.setenv("GT_JIRA_CLIENT_SECRET", "jira_client_secret")
    monkeypatch.setenv("GT_OAUTH_REDIRECT_BASE", "http://localhost:8000")
    monkeypatch.setenv("GT_CONNECTIONS_PATH", "")  # use default; tests do not write
    settings = ApiSettings()
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def plain_client() -> TestClient:
    return TestClient(create_app(ApiSettings()))


def test_github_start_not_configured(plain_client: TestClient) -> None:
    r = plain_client.get("/api/auth/github/start")
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"].lower()


def test_jira_start_not_configured(plain_client: TestClient) -> None:
    r = plain_client.get("/api/auth/jira/start")
    assert r.status_code == 400
    assert "not configured" in r.json()["detail"].lower()


def test_github_start_returns_authorize_url(configured_client: TestClient) -> None:
    r = configured_client.get("/api/auth/github/start")
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert url.startswith("https://github.com/login/oauth/authorize")
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["client_id"] == ["gh_client_id"]
    assert "state" in qs


def test_jira_start_returns_authorize_url_with_pkce(configured_client: TestClient) -> None:
    r = configured_client.get("/api/auth/jira/start")
    assert r.status_code == 200
    url = r.json()["authorize_url"]
    assert url.startswith("https://auth.atlassian.com/authorize")
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    assert qs["client_id"] == ["jira_client_id"]
    assert qs["code_challenge_method"] == ["S256"]
    assert "state" in qs
    assert "code_challenge" in qs


def test_callback_rejects_invalid_state(configured_client: TestClient) -> None:
    r = configured_client.get("/api/auth/github/callback?code=abc&state=nope")
    assert r.status_code == 200
    assert "Invalid or expired OAuth state" in r.text
