"""Tests for the encrypted connection store."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from groundtruth.connections.store import ConnectionStore
from groundtruth.safety.secrets import DecryptError


@pytest.fixture
def secret_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = "m7RGYJ8vCR2xWgS3_KzR3yNqLEpT6uVvZ7wX9yZ0abc="
    monkeypatch.setenv("GT_SECRET_KEY", key)
    return key


@pytest.fixture
def store(tmp_path: Path, secret_key: str) -> ConnectionStore:
    return ConnectionStore(path=tmp_path / "connections.json")


def test_github_token_roundtrip(store: ConnectionStore) -> None:
    store.set_github(
        auth_kind="pat",
        repo_owner="acme",
        repo_name="widgets",
        token="ghp_supersecrettoken1234567890abcdefghijklmnopqrstuvwxyz",
    )
    assert store.github_token() == "ghp_supersecrettoken1234567890abcdefghijklmnopqrstuvwxyz"


def test_wrong_key_fails_with_decrypt_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GT_SECRET_KEY", "m7RGYJ8vCR2xWgS3_KzR3yNqLEpT6uVvZ7wX9yZ0abc=")
    store = ConnectionStore(path=tmp_path / "connections.json")
    store.set_github(auth_kind="pat", repo_owner="o", repo_name="n", token="secret-token")

    monkeypatch.setenv("GT_SECRET_KEY", "a7RGYJ8vCR2xWgS3_KzR3yNqLEpT6uVvZ7wX9yZ0xyz=")
    with pytest.raises(DecryptError):
        store.github_token()


def test_no_plaintext_secret_on_disk(store: ConnectionStore, tmp_path: Path) -> None:
    token = "ghp_supersecrettoken1234567890abcdefghijklmnopqrstuvwxyz"
    store.set_github(auth_kind="pat", repo_owner="o", repo_name="n", token=token)
    raw = (tmp_path / "connections.json").read_text(encoding="utf-8")
    assert token not in raw
    assert "token_enc" in raw


def test_corrupt_store_falls_back_to_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GT_SECRET_KEY", "m7RGYJ8vCR2xWgS3_KzR3yNqLEpT6uVvZ7wX9yZ0abc=")
    path = tmp_path / "connections.json"
    path.write_text("not json", encoding="utf-8")
    store = ConnectionStore(path=path)
    doc = store.load()
    assert doc.github.repo_owner == ""
    assert doc.jira.site_url == ""


def test_jira_oauth_store_roundtrip(store: ConnectionStore) -> None:
    store.set_jira(
        auth_kind="oauth",
        site_url="https://acme.atlassian.net",
        project_key="GT",
        access_token="atlassian-oauth-access",
        refresh_token="atlassian-refresh",
        cloud_id="1234-5678",
        scopes=["read:jira-work"],
        expires_at="2026-09-04T12:00:00+00:00",
    )
    assert store.jira_access_token() == "atlassian-oauth-access"
    assert store.jira_refresh_token() == "atlassian-refresh"
