"""Encrypted connection store persisted as JSON.

Metadata is stored in cleartext; only secret values are encrypted with the
project-wide Fernet key. Response models must never expose decrypted secrets.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from groundtruth.config import PROJECT_ROOT
from groundtruth.safety.secrets import DecryptError, encrypt as _encrypt, decrypt as _decrypt


CONNECTIONS_PATH = Path(
    os.getenv("GT_CONNECTIONS_PATH", PROJECT_ROOT / ".groundtruth" / "connections.json")
).resolve()


class GitHubConnection(BaseModel):
    auth_kind: Literal["pat", "oauth"] = "pat"
    repo_owner: str = ""
    repo_name: str = ""
    login: str = ""
    scopes: list[str] = Field(default_factory=list)
    token_enc: str = ""  # PAT or OAuth access token
    connected_at: str = ""


class JiraConnection(BaseModel):
    auth_kind: Literal["basic", "oauth"] = "basic"
    site_url: str = ""  # e.g. https://x.atlassian.net
    cloud_id: str = ""
    project_key: str = ""
    email: str = ""
    access_token_enc: str = ""
    refresh_token_enc: str = ""
    scopes: list[str] = Field(default_factory=list)
    expires_at: str = ""  # ISO-8601, empty means unknown/no expiry
    connected_at: str = ""


class LlmConnection(BaseModel):
    provider: str = ""
    base_url: str = ""
    model: str = ""
    api_key_enc: str = ""
    key_last4: str = ""
    connected_at: str = ""


class ConnectionsDoc(BaseModel):
    version: int = 1
    github: GitHubConnection = Field(default_factory=GitHubConnection)
    jira: JiraConnection = Field(default_factory=JiraConnection)
    llm: LlmConnection = Field(default_factory=LlmConnection)


class ConnectionStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or CONNECTIONS_PATH).resolve()

    def load(self) -> ConnectionsDoc:
        if not self.path.exists():
            return ConnectionsDoc()
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return ConnectionsDoc()
        try:
            return ConnectionsDoc.model_validate(doc)
        except Exception:
            return ConnectionsDoc()

    def _save(self, doc: ConnectionsDoc) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(
            doc.model_dump_json(indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    def set_github(
        self,
        *,
        auth_kind: Literal["pat", "oauth"],
        repo_owner: str,
        repo_name: str,
        token: str,
        login: str = "",
        scopes: list[str] | None = None,
    ) -> None:
        doc = self.load()
        doc.github = GitHubConnection(
            auth_kind=auth_kind,
            repo_owner=repo_owner,
            repo_name=repo_name,
            token_enc=_encrypt(token) if token else "",
            login=login,
            scopes=scopes or [],
            connected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save(doc)

    def set_jira(
        self,
        *,
        auth_kind: Literal["basic", "oauth"],
        site_url: str,
        project_key: str,
        email: str = "",
        access_token: str = "",
        api_token: str = "",
        refresh_token: str = "",
        cloud_id: str = "",
        scopes: list[str] | None = None,
        expires_at: str = "",
    ) -> None:
        doc = self.load()
        # For basic auth, access_token_enc holds the API token paired with email.
        secret = access_token if auth_kind == "oauth" else api_token
        doc.jira = JiraConnection(
            auth_kind=auth_kind,
            site_url=site_url.rstrip("/"),
            cloud_id=cloud_id,
            project_key=project_key.upper(),
            email=email,
            access_token_enc=_encrypt(secret) if secret else "",
            refresh_token_enc=_encrypt(refresh_token) if refresh_token else "",
            scopes=scopes or [],
            expires_at=expires_at,
            connected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save(doc)

    def set_llm(
        self,
        *,
        provider: str,
        base_url: str,
        model: str,
        api_key: str,
    ) -> None:
        doc = self.load()
        last4 = api_key[-4:] if len(api_key) >= 4 else ""
        doc.llm = LlmConnection(
            provider=provider,
            base_url=base_url.rstrip("/"),
            model=model,
            api_key_enc=_encrypt(api_key) if api_key else doc.llm.api_key_enc,
            key_last4=last4 if api_key else doc.llm.key_last4,
            connected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._save(doc)

    def update_github_repo(self, owner: str, name: str) -> None:
        doc = self.load()
        doc.github.repo_owner = owner
        doc.github.repo_name = name
        self._save(doc)

    def update_jira_project(self, site_url: str, project_key: str) -> None:
        doc = self.load()
        doc.jira.site_url = site_url.rstrip("/")
        doc.jira.project_key = project_key.upper()
        self._save(doc)

    def clear(self, provider: Literal["github", "jira", "llm"]) -> None:
        doc = self.load()
        setattr(doc, provider, type(getattr(doc, provider))())
        self._save(doc)

    def github_token(self) -> str:
        token = self.load().github.token_enc
        return _decrypt(token) if token else ""

    def jira_access_token(self) -> str:
        token = self.load().jira.access_token_enc
        return _decrypt(token) if token else ""

    def jira_refresh_token(self) -> str:
        token = self.load().jira.refresh_token_enc
        return _decrypt(token) if token else ""

    def llm_api_key(self) -> str:
        token = self.load().llm.api_key_enc
        return _decrypt(token) if token else ""

    def all_secret_values(self) -> list[str]:
        """Return all live plaintext secrets for value-based redaction."""
        secrets: list[str] = []
        try:
            secrets.append(self.github_token())
            secrets.append(self.jira_access_token())
            secrets.append(self.jira_refresh_token())
            secrets.append(self.llm_api_key())
        except DecryptError:
            pass
        return [s for s in secrets if len(s) >= 12]
