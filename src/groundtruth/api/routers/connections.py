"""Connection management endpoints for Settings UI.

Tokens are stored encrypted and are never returned in status responses.
"""

from __future__ import annotations

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from groundtruth.api.schemas import (
    ConnectionTestResult,
    ConnectionsStatus,
    ParsedUrlResponse,
)
from groundtruth.api.settings import ApiSettings
from groundtruth.connections.store import ConnectionStore
from groundtruth.connections.urls import parse_github_repo_url, parse_jira_url
from groundtruth.safety.redact import redact


class ParseUrlRequest(BaseModel):
    url: str


class GitHubRepoRequest(BaseModel):
    owner: str
    name: str


class GitHubPatRequest(BaseModel):
    owner: str
    name: str
    pat: str


class JiraProjectRequest(BaseModel):
    base_url: str
    project_key: str


class JiraBasicRequest(BaseModel):
    base_url: str
    project_key: str
    email: str
    api_token: str


class LlmRequest(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key: str


router = APIRouter(prefix="/api/connections", tags=["connections"])


def _store(request: Request) -> ConnectionStore:
    return request.app.state.connections_store


def _settings(request: Request) -> ApiSettings:
    return request.app.state.settings


@router.get("", response_model=ConnectionsStatus)
def get_connections(request: Request) -> dict:
    store = _store(request)
    settings = _settings(request)
    doc = store.load()
    gh = doc.github
    jira = doc.jira
    llm = doc.llm
    return {
        "github": {
            "connected": bool(gh.repo_owner and gh.repo_name and gh.token_enc),
            "auth_kind": gh.auth_kind,
            "repo_slug": f"{gh.repo_owner}/{gh.repo_name}" if gh.repo_owner and gh.repo_name else "",
            "login": gh.login,
            "scopes": gh.scopes,
            "oauth_available": settings.github_oauth_available,
        },
        "jira": {
            "connected": bool(jira.site_url and jira.project_key and jira.access_token_enc),
            "auth_kind": jira.auth_kind,
            "site_url": jira.site_url,
            "project_key": jira.project_key,
            "email": jira.email,
            "oauth_available": settings.jira_oauth_available,
        },
        "llm": {
            "connected": bool(llm.api_key_enc and llm.model and llm.base_url),
            "provider": llm.provider,
            "base_url": llm.base_url,
            "model": llm.model,
            "key_last4": llm.key_last4,
        },
    }


@router.post("/parse-url", response_model=ParsedUrlResponse)
def parse_url(payload: ParseUrlRequest) -> dict:
    raw = payload.url.strip()
    host = raw.lower().split("/")[2] if "//" in raw else raw.lower().split("/")[0]
    if "github.com" in host:
        owner, name = parse_github_repo_url(raw)
        return {
            "provider": "github",
            "valid": bool(owner and name),
            "owner": owner,
            "name": name,
        }
    if "atlassian.net" in host or "/jira" in raw.lower():
        base_url, project_key = parse_jira_url(raw)
        return {
            "provider": "jira",
            "valid": bool(base_url),
            "base_url": base_url,
            "project_key": project_key,
        }
    raise HTTPException(status_code=400, detail="Unrecognized URL: paste a GitHub repo or Jira project URL")


@router.post("/github/repo")
def set_github_repo(payload: GitHubRepoRequest, request: Request) -> dict:
    _store(request).update_github_repo(payload.owner, payload.name)
    return {"ok": True}


@router.post("/github/pat")
def set_github_pat(payload: GitHubPatRequest, request: Request) -> dict:
    store = _store(request)
    store.set_github(
        auth_kind="pat",
        repo_owner=payload.owner,
        repo_name=payload.name,
        token=payload.pat,
    )
    return {"ok": True}


@router.post("/jira/project")
def set_jira_project(payload: JiraProjectRequest, request: Request) -> dict:
    _store(request).update_jira_project(payload.base_url, payload.project_key)
    return {"ok": True}


@router.post("/jira/basic")
def set_jira_basic(payload: JiraBasicRequest, request: Request) -> dict:
    store = _store(request)
    store.set_jira(
        auth_kind="basic",
        site_url=payload.base_url,
        project_key=payload.project_key,
        email=payload.email,
        api_token=payload.api_token,
    )
    return {"ok": True}


@router.post("/llm")
def set_llm(payload: LlmRequest, request: Request) -> dict:
    store = _store(request)
    store.set_llm(
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
    )
    return {"ok": True}


@router.delete("/{provider}")
def clear_connection(provider: Literal["github", "jira", "llm"], request: Request) -> dict:
    _store(request).clear(provider)
    return {"ok": True}


@router.post("/{provider}/test", response_model=ConnectionTestResult)
def test_connection(provider: Literal["github", "jira", "llm"], request: Request) -> dict:
    store = _store(request)
    if provider == "github":
        return _test_github(store)
    if provider == "jira":
        return _test_jira(store)
    return _test_llm(store)


def _test_github(store: ConnectionStore) -> dict:
    doc = store.load().github
    token = store.github_token() if doc.token_enc else ""
    if not token:
        return {"ok": False, "message": "No GitHub token stored"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    slug = f"{doc.repo_owner}/{doc.repo_name}" if doc.repo_owner and doc.repo_name else ""
    url = f"https://api.github.com/repos/{slug}" if slug else "https://api.github.com/user"
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            login = data.get("login") or data.get("full_name") or slug
            return {"ok": True, "message": f"Connected as {login}"}
        return {"ok": False, "message": redact(f"GitHub returned HTTP {response.status_code}")}
    except Exception as exc:
        return {"ok": False, "message": redact(str(exc))}


def _test_jira(store: ConnectionStore) -> dict:
    doc = store.load().jira
    token = store.jira_access_token() if doc.access_token_enc else ""
    if not token:
        return {"ok": False, "message": "No Jira token stored"}
    if not doc.site_url:
        return {"ok": False, "message": "No Jira site URL stored"}

    if doc.auth_kind == "oauth":
        if not doc.cloud_id:
            return {"ok": False, "message": "Jira OAuth is missing cloud ID"}
        url = f"https://api.atlassian.com/ex/jira/{doc.cloud_id}/rest/api/3/myself"
        headers = {"Authorization": f"Bearer {token}"}
        auth = None
    else:
        email = doc.email
        if not email:
            return {"ok": False, "message": "No Jira email stored"}
        url = f"{doc.site_url.rstrip('/')}/rest/api/3/myself"
        headers = {}
        auth = (email, token)

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=headers, auth=auth)
        if response.status_code == 200:
            data = response.json()
            display = data.get("displayName") or data.get("emailAddress") or doc.email or "Jira"
            return {"ok": True, "message": f"Connected as {display}"}
        return {"ok": False, "message": redact(f"Jira returned HTTP {response.status_code}")}
    except Exception as exc:
        return {"ok": False, "message": redact(str(exc))}


def _test_llm(store: ConnectionStore) -> dict:
    doc = store.load().llm
    key = store.llm_api_key() if doc.api_key_enc else ""
    if not key or not doc.base_url:
        return {"ok": False, "message": "No LLM key or base URL stored"}
    url = f"{doc.base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {key}"}
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, headers=headers)
        if response.status_code in (200, 404):
            # 404 means the endpoint does not exist but the server is reachable.
            return {"ok": True, "message": f"Reachable ({response.status_code})"}
        return {"ok": False, "message": redact(f"LLM returned HTTP {response.status_code}")}
    except Exception as exc:
        return {"ok": False, "message": redact(str(exc))}
