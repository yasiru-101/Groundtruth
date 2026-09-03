"""Derived views over the artifact repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from groundtruth.api.normalize import format_datetime, parse_datetime
from groundtruth.api.repository import ArtifactRepository
from groundtruth.ledger.reader import read_entries, verify_chain


def _score_total(score_doc: dict[str, Any]) -> float:
    score = score_doc.get("score", {})
    return float(score.get("total", 0.0))


def _score_as_of(score_doc: dict[str, Any]) -> str | None:
    score = score_doc.get("score", {})
    return format_datetime(score.get("as_of"))


def _score_policy_hash(score_doc: dict[str, Any]) -> str:
    score = score_doc.get("score", {})
    return str(score.get("policy_hash", ""))


def build_score_history(repo: ArtifactRepository) -> list[dict[str, Any]]:
    """Newest-first list of score history points."""
    history: list[dict[str, Any]] = []
    for run_dir, doc in repo.all_score_runs():
        as_of = _score_as_of(doc) or format_datetime(run_dir.stat().st_mtime)
        history.append(
            {
                "run_id": doc.get("score", {}).get("run_id", repo.run_id_from_dir(run_dir)),
                "run_dir": run_dir.name,
                "as_of": as_of,
                "total": _score_total(doc),
                "policy_hash": _score_policy_hash(doc),
            }
        )
    return history


def compare_score_runs(
    repo: ArtifactRepository, before_id: str, after_id: str
) -> dict[str, Any]:
    """Compare two score runs by run directory name."""
    before_doc: dict[str, Any] | None = None
    after_doc: dict[str, Any] | None = None
    before_dir: Path | None = None
    after_dir: Path | None = None

    for run_dir, doc in repo.all_score_runs():
        if run_dir.name == before_id:
            before_doc = doc
            before_dir = run_dir
        if run_dir.name == after_id:
            after_doc = doc
            after_dir = run_dir

    if before_doc is None or after_doc is None:
        raise ValueError("before or after run not found")

    before_total = _score_total(before_doc)
    after_total = _score_total(after_doc)

    before_dims = {d.get("name"): d for d in before_doc.get("score", {}).get("dimensions", [])}
    after_dims = {d.get("name"): d for d in after_doc.get("score", {}).get("dimensions", [])}

    dimensions_changed = []
    for name in sorted(set(before_dims) | set(after_dims)):
        bv = before_dims.get(name, {}).get("value")
        av = after_dims.get(name, {}).get("value")
        if bv != av:
            dimensions_changed.append(
                {
                    "name": name,
                    "before": bv,
                    "after": av,
                }
            )

    before_discrepancies = set()
    after_discrepancies = set()
    for run_dir, doc in repo.all_audit_runs():
        ids = {d.get("discrepancy_id") for d in doc.get("discrepancies", [])}
        if run_dir.name == before_id:
            before_discrepancies = ids
        if run_dir.name == after_id:
            after_discrepancies = ids

    return {
        "before": {
            "run_id": before_id,
            "run_dir": before_dir.name,
            "as_of": _score_as_of(before_doc),
            "total": before_total,
            "policy_hash": _score_policy_hash(before_doc),
        },
        "after": {
            "run_id": after_id,
            "run_dir": after_dir.name,
            "as_of": _score_as_of(after_doc),
            "total": after_total,
            "policy_hash": _score_policy_hash(after_doc),
        },
        "delta": round(after_total - before_total, 4),
        "dimensions_changed": dimensions_changed,
        "resolved": sorted(before_discrepancies - after_discrepancies),
        "introduced": sorted(after_discrepancies - before_discrepancies),
    }


def build_agent_summary(repo: ArtifactRepository) -> dict[str, Any]:
    """Aggregate ledger entries by actor."""
    actors: dict[str, dict[str, Any]] = {}
    total_actions = 0
    refusals = 0

    for ledger_path in repo.all_ledger_paths():
        for entry in read_entries(ledger_path):
            actor = entry.get("actor", "unknown")
            if actor not in actors:
                actors[actor] = {
                    "actor": actor,
                    "action_count": 0,
                    "last_action": None,
                    "last_subject": None,
                    "last_ts": None,
                }
            actors[actor]["action_count"] += 1
            total_actions += 1
            ts = entry.get("ts")
            if ts and (actors[actor]["last_ts"] is None or ts > actors[actor]["last_ts"]):
                actors[actor]["last_ts"] = format_datetime(ts)
                actors[actor]["last_action"] = entry.get("action")
                actors[actor]["last_subject"] = entry.get("subject")
            if entry.get("outcome") == "refused":
                refusals += 1

    return {
        "actors": sorted(actors.values(), key=lambda a: a["action_count"], reverse=True),
        "total_actions": total_actions,
        "refusals": refusals,
    }


def build_activity_feed(repo: ArtifactRepository) -> list[dict[str, Any]]:
    """Flatten all ledger entries into a single newest-first feed."""
    feed: list[dict[str, Any]] = []
    for ledger_path in repo.all_ledger_paths():
        for entry in read_entries(ledger_path):
            feed.append(
                {
                    "seq": entry.get("seq"),
                    "run_id": entry.get("run_id"),
                    "entry_id": entry.get("entry_id"),
                    "ts": format_datetime(entry.get("ts")),
                    "actor": entry.get("actor", "unknown"),
                    "action": entry.get("action", ""),
                    "mode": entry.get("mode", ""),
                    "subject": entry.get("subject", ""),
                    "outcome": entry.get("outcome", ""),
                    "error": entry.get("error"),
                    "evidence": entry.get("evidence", []),
                }
            )
    feed.sort(key=lambda e: (e["ts"] or "", e["seq"] or 0), reverse=True)
    return feed


def verify_all_ledgers(repo: ArtifactRepository) -> list[dict[str, Any]]:
    """Return integrity verdicts for every ledger."""
    results = []
    for ledger_path in repo.all_ledger_paths():
        run_dir = ledger_path.parent.name
        try:
            entries = verify_chain(ledger_path)
            results.append(
                {
                    "run_dir": run_dir,
                    "ledger_path": str(ledger_path),
                    "valid": True,
                    "entries": len(entries),
                    "error": None,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "run_dir": run_dir,
                    "ledger_path": str(ledger_path),
                    "valid": False,
                    "entries": 0,
                    "error": str(exc),
                }
            )
    return results


def list_changesets(repo: ArtifactRepository) -> list[dict[str, Any]]:
    """Load changeset files if present."""
    changesets_dir = repo.artifacts_dir / "changesets"
    if not changesets_dir.exists():
        return []
    results = []
    for path in sorted(changesets_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        results.append(
            {
                "hash": path.stem,
                "description": doc.get("description", ""),
                "items": doc.get("items", []),
            }
        )
    return results
