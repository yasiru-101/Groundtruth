"""OAuth helpers for GitHub and Jira connection flows."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse
from typing import Any

import httpx


class OAuthStateStore:
    """In-memory, single-use OAuth state store with a TTL and optional PKCE."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self._states: dict[str, tuple[float, str]] = {}
        self._ttl = ttl_seconds

    def issue(self, use_pkce: bool = False) -> tuple[str, str, str | None]:
        """Return (state, code_challenge, code_verifier). verifier is None when not using PKCE."""
        state = secrets.token_urlsafe(32)
        verifier: str | None = None
        challenge = ""
        if use_pkce:
            verifier = secrets.token_urlsafe(48)
            challenge = _pkce_challenge(verifier)
        self._states[state] = (time.time() + self._ttl, verifier or "")
        return state, challenge, verifier

    def _purge_expired(self) -> None:
        now = time.time()
        expired = [s for s, (expires_at, _) in self._states.items() if expires_at < now]
        for s in expired:
            del self._states[s]

    def consume(self, state: str) -> tuple[bool, str]:
        """Return (ok, code_verifier). verifier is empty when PKCE was not used."""
        if not state:
            return False, ""
        self._purge_expired()
        for key in list(self._states.keys()):
            if hmac.compare_digest(key, state):
                verifier = self._states[key][1]
                del self._states[key]
                return True, verifier
        return False, ""


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class GitHubOAuth:
    """GitHub OAuth App authorization-code flow."""

    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USER_URL = "https://api.github.com/user"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorize_url(self, state: str, scope: str = "repo,read:org") -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "state": state,
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"GitHub token exchange returned non-JSON: {resp.text}") from exc

        if "error" in data:
            raise RuntimeError(
                f"GitHub OAuth error: {data.get('error_description', data['error'])}"
            )
        if "access_token" not in data:
            raise RuntimeError("GitHub token exchange did not return an access token")
        return data

    async def fetch_user(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
        resp.raise_for_status()
        return resp.json()


class JiraOAuth:
    """Jira Cloud OAuth 2.0 3LO (authorization-code flow with PKCE/S256)."""

    AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
    TOKEN_URL = "https://auth.atlassian.com/oauth/token"
    RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"

    SCOPES = "read:jira-work read:jira-user write:jira-work offline_access"

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def authorize_url(self, state: str, code_challenge: str) -> str:
        params = {
            "audience": "api.atlassian.com",
            "client_id": self.client_id,
            "scope": self.SCOPES,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "response_type": "code",
            "prompt": "consent",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    async def exchange(self, code: str, code_verifier: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                    "code_verifier": code_verifier,
                },
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Jira token exchange returned non-JSON: {resp.text}") from exc

        if resp.status_code >= 400 or "error" in data:
            raise RuntimeError(
                f"Jira OAuth error: {data.get('error_description', data.get('error', resp.status_code))}"
            )
        if "access_token" not in data:
            raise RuntimeError("Jira token exchange did not return an access token")
        return data

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/json"},
                json={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                },
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Jira refresh returned non-JSON: {resp.text}") from exc

        if resp.status_code >= 400 or "error" in data:
            raise RuntimeError(
                f"Jira refresh error: {data.get('error_description', data.get('error', resp.status_code))}"
            )
        if "access_token" not in data:
            raise RuntimeError("Jira refresh did not return an access token")
        return data

    async def accessible_resources(self, access_token: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.RESOURCES_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
        resp.raise_for_status()
        return resp.json()
