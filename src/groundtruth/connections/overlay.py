"""Overlay stored connections onto the process-wide Settings object."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from groundtruth.api.oauth import JiraOAuth
from groundtruth.config import Settings
from groundtruth.connections.store import ConnectionStore


def _refresh_jira_if_needed(store: ConnectionStore) -> None:
    """Refresh a near-expiry Jira OAuth access token before overlaying it."""
    jira = store.load().jira
    if jira.auth_kind != "oauth" or not jira.refresh_token_enc:
        return

    expires_at = jira.expires_at
    try:
        expiry = datetime.fromisoformat(expires_at) if expires_at else datetime.min.replace(tzinfo=timezone.utc)
    except ValueError:
        expiry = datetime.min.replace(tzinfo=timezone.utc)

    if expiry > datetime.now(timezone.utc) + timedelta(minutes=5):
        return

    client_id = os.getenv("GT_JIRA_CLIENT_ID", "")
    client_secret = os.getenv("GT_JIRA_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return

    redirect_uri = os.getenv("GT_OAUTH_REDIRECT_BASE", "http://localhost:8000") + "/api/auth/jira/callback"
    refresh_token = store.jira_refresh_token()
    if not refresh_token:
        return

    try:
        oauth = JiraOAuth(client_id, client_secret, redirect_uri)
        import asyncio

        token_data = asyncio.run(oauth.refresh(refresh_token))
    except Exception:
        return

    new_access = token_data.get("access_token", "")
    new_refresh = token_data.get("refresh_token", refresh_token)
    expires_in = token_data.get("expires_in")
    new_expires_at = ""
    if expires_in:
        new_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    store.set_jira(
        auth_kind="oauth",
        site_url=jira.site_url,
        project_key=jira.project_key,
        access_token=new_access,
        refresh_token=new_refresh,
        cloud_id=jira.cloud_id,
        scopes=jira.scopes,
        expires_at=new_expires_at,
    )


def apply_connections(settings: Settings) -> Settings:
    """Return a Settings copy with stored connections overlaid onto env values.

    Env tokens remain the fallback. Set GT_USE_CONNECTIONS=0 to disable.
    """
    if os.getenv("GT_USE_CONNECTIONS", "1") == "0":
        return settings

    try:
        store = ConnectionStore()
    except OSError:
        return settings

    updates: dict[str, object] = {}

    # GitHub
    gh = store.load().github
    if gh.repo_owner:
        updates["github_repo_owner"] = gh.repo_owner
    if gh.repo_name:
        updates["github_repo_name"] = gh.repo_name
    gh_token = store.github_token()
    if gh_token:
        updates["github_token"] = gh_token

    # Jira
    _refresh_jira_if_needed(store)
    jira = store.load().jira
    if jira.site_url:
        updates["jira_base_url"] = jira.site_url
    if jira.project_key:
        updates["jira_project_key"] = jira.project_key
    if jira.email:
        updates["jira_email"] = jira.email
    jira_secret = store.jira_access_token()
    if jira_secret:
        if jira.auth_kind == "oauth":
            updates["jira_auth_mode"] = "oauth"
            updates["jira_access_token"] = jira_secret
            updates["jira_cloud_id"] = jira.cloud_id
            updates["jira_api_token"] = ""
        else:
            updates["jira_auth_mode"] = "basic"
            updates["jira_api_token"] = jira_secret
            updates["jira_access_token"] = ""
            updates["jira_cloud_id"] = ""

    # LLM
    llm = store.load().llm
    if llm.api_key_enc:
        key = store.llm_api_key()
        if key:
            updates["llm_api_key"] = key
    if llm.model:
        updates["llm_model"] = llm.model
    if llm.base_url:
        updates["llm_base_url"] = llm.base_url

    if not updates:
        return settings

    return settings.model_copy(update=updates)
