"""Shared helpers for the discrepancy detectors."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from groundtruth.contracts.evidence import Evidence, EvidenceKind


def evidence(
    kind: EvidenceKind,
    ref: str,
    url: str,
    as_of: datetime,
    detail: dict[str, Any] | None = None,
) -> Evidence:
    """Build an Evidence; an empty url falls back to the ref itself."""
    flat = {k: str(v) for k, v in (detail or {}).items()}
    return Evidence(
        kind=kind,
        ref=ref,
        url=url or ref,
        observed_at=as_of,
        detail=flat,
    )
