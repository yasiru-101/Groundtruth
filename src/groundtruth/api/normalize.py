"""Normalize artifact payloads for the dashboard API."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from groundtruth.safety.redact import redact


_UTC = timezone.utc


def _is_space_aware(dt_string: str) -> bool:
    """Detect legacy space-separated timezone offsets like '+00:00'."""
    return bool(re.search(r"\s[+-]\d{2}:\d{2}$", dt_string.strip()))


def parse_datetime(value: Any) -> datetime | None:
    """Parse a datetime from artifact JSON, forgiving several legacy formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=_UTC)
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"nan", "none", "null"}:
        return None

    # Normalize space-separated timezone offset to no space.
    if _is_space_aware(text):
        text = re.sub(r"\s([+-]\d{2}:\d{2})$", r"\1", text)

    # Try ISO formats.
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=_UTC)
            return parsed
        except ValueError:
            continue

    # Fallback to fromisoformat.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_UTC)
        return parsed
    except ValueError:
        return None


def format_datetime(value: Any) -> str | None:
    """Return an ISO datetime string or None."""
    parsed = parse_datetime(value)
    return parsed.isoformat() if parsed else None


def normalize_payload(payload: Any) -> Any:
    """Recursively normalize datetimes and redact secrets in a payload."""
    if isinstance(payload, dict):
        return {k: normalize_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [normalize_payload(v) for v in payload]
    if isinstance(payload, datetime):
        return payload.isoformat()
    if isinstance(payload, str):
        return redact(payload)
    return payload


def safe_read_json(path: Any) -> dict[str, Any]:
    """Read JSON, returning an empty dict on any error."""
    import json

    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text) if text.strip() else {}
    except Exception:
        return {}
