from __future__ import annotations

import hashlib
import json
from pathlib import Path

from groundtruth.contracts.ledger import LedgerEntry


class ChainVerificationError(Exception):
    def __init__(self, seq: int, expected: str, actual: str) -> None:
        self.seq = seq
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Hash chain broken at seq={seq}. "
            f"Expected this_hash={expected}, recomputed={actual}."
        )


def _recompute_hash(entry: dict, prev_hash: str) -> str:
    payload = {
        "seq": entry["seq"],
        "run_id": entry["run_id"],
        "entry_id": entry["entry_id"],
        "ts": entry["ts"],
        "actor": entry["actor"],
        "action": entry["action"],
        "mode": entry["mode"],
        "subject": entry["subject"],
        "inputs_hash": entry["inputs_hash"],
        "outputs_hash": entry["outputs_hash"],
        "evidence": entry["evidence"],
        "approval": entry["approval"],
        "outcome": entry["outcome"],
        "error": entry["error"],
        "prev_hash": prev_hash,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_entries(ledger_path: Path) -> list[dict]:
    entries: list[dict] = []
    if not ledger_path.exists():
        return entries
    with open(ledger_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def verify_chain(ledger_path: Path) -> list[dict]:
    entries = read_entries(ledger_path)
    prev_hash = "GENESIS"

    for entry in entries:
        expected_this_hash = entry["this_hash"]
        recomputed = _recompute_hash(entry, prev_hash)

        if recomputed != expected_this_hash:
            raise ChainVerificationError(
                seq=entry["seq"],
                expected=expected_this_hash,
                actual=recomputed,
            )

        prev_hash = expected_this_hash

    return entries


def project_state(ledger_path: Path) -> dict:
    entries = read_entries(ledger_path)
    state: dict = {
        "total_entries": len(entries),
        "ok_count": 0,
        "refused_count": 0,
        "error_count": 0,
        "actors": set(),
        "actions": set(),
        "subjects": set(),
    }
    for entry in entries:
        outcome = entry.get("outcome", "")
        if outcome == "ok":
            state["ok_count"] += 1
        elif outcome == "refused":
            state["refused_count"] += 1
        elif outcome == "error":
            state["error_count"] += 1
        state["actors"].add(entry.get("actor", ""))
        state["actions"].add(entry.get("action", ""))
        state["subjects"].add(entry.get("subject", ""))
    state["actors"] = sorted(state["actors"])
    state["actions"] = sorted(state["actions"])
    state["subjects"] = sorted(state["subjects"])
    return state
