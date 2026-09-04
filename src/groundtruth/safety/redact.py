from __future__ import annotations

import re

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("gho_token", re.compile(r"gho_[A-Za-z0-9]{36,}")),
    ("ghp_token", re.compile(r"ghp_[A-Za-z0-9]{36,}")),
    ("ghu_token", re.compile(r"ghu_[A-Za-z0-9]{36,}")),
    ("github_pat", re.compile(r"github_pat_[A-Za-z0-9_\-]{22,}")),
    ("ghs_token", re.compile(r"ghs_[A-Za-z0-9]{36,}")),
    ("ghr_token", re.compile(r"ghr_[A-Za-z0-9]{36,}")),
    ("jira_token", re.compile(r"ATATT[A-Za-z0-9_\-]{20,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]+")),
    ("generic_api_key", re.compile(r"(?i)(api[_-]?key|api[_-]?token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}['\"]?")),
    ("fernet", re.compile(r"gAAAA[A-Za-z0-9_\-]{20,}")),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    result = text
    for _name, pattern in _PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_values(text: str, secrets: list[str]) -> str:
    """Redact exact secret strings (e.g. stored OAuth/LLM tokens) from text."""
    result = text
    for secret in secrets:
        if len(secret) >= 8:
            result = result.replace(secret, REDACTED)
    return result


def redact_dict(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = redact(v)
        elif isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, list):
            out[k] = redact_list(v)
        else:
            out[k] = v
    return out


def redact_list(data: list) -> list:
    out = []
    for item in data:
        if isinstance(item, str):
            out.append(redact(item))
        elif isinstance(item, dict):
            out.append(redact_dict(item))
        elif isinstance(item, list):
            out.append(redact_list(item))
        else:
            out.append(item)
    return out
