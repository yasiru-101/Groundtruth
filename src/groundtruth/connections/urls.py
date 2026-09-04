"""URL parsers that turn user-pasted links into structured connection info."""

from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs

from groundtruth.safety.git_guard import normalize_repo_slug


def parse_github_repo_url(raw: str) -> tuple[str, str]:
    """Reduce any GitHub URL to (owner, name). Returns ("", "") on failure."""
    raw = raw.strip()
    if not raw:
        return ("", "")

    # normalize_repo_slug handles git@, ssh://, https://, and .git suffixes.
    slug = normalize_repo_slug(raw)
    if not slug:
        return ("", "")

    # Drop any path/query fragments that may trail the owner/name.
    # normalize_repo_slug returns exactly owner/name for clone URLs; for web
    # URLs we still have the path after the host.
    parts = [p for p in slug.split("/") if p]
    if len(parts) < 2:
        return ("", "")

    owner, name = parts[0], parts[1]
    segment_re = re.compile(r"^[A-Za-z0-9._-]+$")
    if not segment_re.match(owner) or not segment_re.match(name):
        return ("", "")
    if owner in (".", "..") or name in (".", ".."):
        return ("", "")
    return (owner, name)


def _extract_jira_project_key(path: str, query: str) -> str:
    # /jira/software/projects/ABC/boards/1 or /jira/software/c/projects/ABC/...
    m = re.search(r"/projects/([A-Z][A-Z0-9_]{0,29})(?:/|$)", path, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # /browse/ABC-123 -> ABC
    m = re.search(r"/browse/([A-Z][A-Z0-9_]{0,29})-\d+", path, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # RapidBoard query param
    qs = parse_qs(query)
    for key in ("projectKey", "selectedProjectKey"):
        if key in qs and qs[key][0]:
            pk = qs[key][0].strip().upper()
            if re.match(r"^[A-Z][A-Z0-9_]{0,29}$", pk):
                return pk
    return ""


def parse_jira_url(raw: str) -> tuple[str, str]:
    """Return (base_url, project_key) from a Jira Cloud URL.

    Base URL always has a scheme and no trailing slash. project_key may be
    empty if the URL does not contain one.
    """
    raw = raw.strip()
    if not raw:
        return ("", "")

    # Force a scheme so urlparse treats it as a netloc.
    if "//" not in raw and not raw.startswith("http"):
        raw = "https://" + raw

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return ("", "")

    host = (parsed.hostname or "").lower().strip()
    if not host or "." not in host:
        return ("", "")

    base_url = f"{parsed.scheme}://{host}"
    project_key = _extract_jira_project_key(parsed.path or "", parsed.query or "")
    return (base_url, project_key)


def parse_llm_base_url(raw: str) -> str:
    """Strip trailing /chat/completions and trailing slashes."""
    raw = raw.strip()
    if raw.endswith("/chat/completions"):
        raw = raw[: -len("/chat/completions")]
    return raw.rstrip("/")
