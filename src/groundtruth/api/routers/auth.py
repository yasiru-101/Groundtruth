"""OAuth callback and authorization-entry endpoints."""

from __future__ import annotations

import html
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from groundtruth.api.oauth import GitHubOAuth, JiraOAuth
from groundtruth.api.schemas import OAuthStartResponse
from groundtruth.safety.redact import redact

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _callback_html(status: str, detail: str, provider: str = "") -> HTMLResponse:
    """Render a small bridge page that posts the result back to the opener."""
    payload = {
        "source": "groundtruth-oauth",
        "status": status,
        "detail": detail,
        "provider": provider,
    }
    # Embed the payload as a JSON/JS object literal so the page does not parse strings.
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    content = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>OAuth Callback</title>
</head>
<body>
  <p>Completing connection…</p>
  <script>
    (function () {{
      var payload = {payload_json};
      try {{
        if (window.opener) {{
          window.opener.postMessage(payload, window.location.origin);
        }}
      }} catch (e) {{}}
      try {{
        window.history.replaceState({{}}, document.title, window.location.pathname + window.location.hash);
      }} catch (e) {{}}
      setTimeout(function () {{
        window.location.href = "/settings?connected=" + encodeURIComponent(payload.provider || "");
      }}, 1500);
    }})();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=content)


def _github_oauth(request: Request) -> GitHubOAuth:
    settings = request.app.state.settings
    redirect_uri = f"{settings.oauth_redirect_base}/api/auth/github/callback"
    return GitHubOAuth(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        redirect_uri=redirect_uri,
    )


def _jira_oauth(request: Request) -> JiraOAuth:
    settings = request.app.state.settings
    redirect_uri = f"{settings.oauth_redirect_base}/api/auth/jira/callback"
    return JiraOAuth(
        client_id=settings.jira_client_id,
        client_secret=settings.jira_client_secret,
        redirect_uri=redirect_uri,
    )


@router.get("/{provider}/start", response_model=OAuthStartResponse)
def start_auth(request: Request, provider: str) -> dict[str, str]:
    settings = request.app.state.settings
    store = request.app.state.oauth_state_store

    if provider == "github":
        if not settings.github_oauth_available:
            raise HTTPException(status_code=400, detail="GitHub OAuth is not configured")
        state, _, _ = store.issue(use_pkce=False)
        return {"authorize_url": _github_oauth(request).authorize_url(state)}

    if provider == "jira":
        if not settings.jira_oauth_available:
            raise HTTPException(status_code=400, detail="Jira OAuth is not configured")
        state, challenge, _ = store.issue(use_pkce=True)
        return {"authorize_url": _jira_oauth(request).authorize_url(state, challenge)}

    raise HTTPException(status_code=404, detail="provider not found")


@router.get("/{provider}/callback")
async def auth_callback(
    request: Request,
    provider: str,
    code: str = "",
    state: str = "",
) -> HTMLResponse:
    settings = request.app.state.settings
    store = request.app.state.oauth_state_store
    connections_store = request.app.state.connections_store

    ok, code_verifier = store.consume(state)
    if not ok:
        return _callback_html(
            status="error",
            detail="Invalid or expired OAuth state. Please try again.",
            provider=provider,
        )

    if provider == "github":
        if not code:
            return _callback_html(
                status="error",
                detail="GitHub did not return an authorization code.",
                provider=provider,
            )
        oauth = _github_oauth(request)
        try:
            token_data = await oauth.exchange(code)
        except Exception as exc:
            return _callback_html(
                status="error",
                detail=redact(str(exc)),
                provider=provider,
            )

        access_token = token_data["access_token"]
        try:
            user_data = await oauth.fetch_user(access_token)
        except Exception as exc:
            return _callback_html(
                status="error",
                detail=redact(str(exc)),
                provider=provider,
            )

        login = user_data.get("login", "")
        scopes = [s.strip() for s in token_data.get("scope", "").split(",") if s.strip()]
        existing = connections_store.load().github
        connections_store.set_github(
            auth_kind="oauth",
            repo_owner=existing.repo_owner,
            repo_name=existing.repo_name,
            token=access_token,
            login=login,
            scopes=scopes,
        )
        return _callback_html(
            status="success",
            detail=f"Connected as @{html.escape(login)}" if login else "Connected",
            provider=provider,
        )

    if provider == "jira":
        if not code:
            return _callback_html(
                status="error",
                detail="Jira did not return an authorization code.",
                provider=provider,
            )
        oauth = _jira_oauth(request)
        try:
            token_data = await oauth.exchange(code, code_verifier)
        except Exception as exc:
            return _callback_html(
                status="error",
                detail=redact(str(exc)),
                provider=provider,
            )

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token", "")
        expires_in = token_data.get("expires_in")
        try:
            resources = await oauth.accessible_resources(access_token)
        except Exception as exc:
            return _callback_html(
                status="error",
                detail=redact(str(exc)),
                provider=provider,
            )

        existing = connections_store.load().jira
        site_url = existing.site_url
        cloud_id = ""
        if resources:
            # Prefer the resource whose site URL matches the stored project site.
            matched = None
            if site_url:
                site_host = site_url.rstrip("/").split("://")[-1].lower()
                for resource in resources:
                    url = (resource.get("url") or "").rstrip("/")
                    if url.lower().endswith(site_host) or site_host in url.lower():
                        matched = resource
                        break
            chosen = matched or resources[0]
            cloud_id = chosen.get("id", "")
            site_url = chosen.get("url", site_url)

        from datetime import datetime, timedelta, timezone

        expires_at = ""
        if expires_in:
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        connections_store.set_jira(
            auth_kind="oauth",
            site_url=site_url,
            project_key=existing.project_key,
            access_token=access_token,
            refresh_token=refresh_token,
            cloud_id=cloud_id,
            scopes=[s.strip() for s in JiraOAuth.SCOPES.split(",") if s.strip()],
            expires_at=expires_at,
        )
        return _callback_html(
            status="success",
            detail=f"Connected to {html.escape(site_url)}" if site_url else "Connected",
            provider=provider,
        )

    return _callback_html(
        status="error",
        detail="Unknown provider.",
        provider=provider,
    )
