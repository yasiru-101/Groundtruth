from __future__ import annotations

import hashlib
import re
import unicodedata


def idempotency_key(source_doc_id: str, normalized_ac_text: str) -> str:
    raw = f"{source_doc_id}\n{normalized_ac_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def discrepancy_id(discrepancy_type: str, subject: str, evidence_refs: list[str]) -> str:
    raw = f"{discrepancy_type}|{subject}|{','.join(sorted(evidence_refs))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def branch_slug(jira_key: str) -> str:
    slug = unicodedata.normalize("NFKD", jira_key)
    slug = re.sub(r"[^a-zA-Z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-").lower()
    return slug or "unnamed"


def content_hash(*parts: str) -> str:
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
