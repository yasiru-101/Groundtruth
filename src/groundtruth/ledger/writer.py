from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from groundtruth.contracts.ledger import ApprovalRef, LedgerEntry, LedgerMode, LedgerOutcome
from groundtruth.safety.redact import redact


def _entry_hash(entry: dict, prev_hash: str) -> str:
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


class LedgerWriter:
    def __init__(self, ledger_path: Path, run_id: str = "") -> None:
        self.ledger_path = ledger_path
        self.run_id = run_id or str(uuid.uuid4())
        self._seq = 0
        self._prev_hash = "GENESIS"

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

        if self.ledger_path.exists():
            self._replay_seq()

    def _replay_seq(self) -> None:
        with open(self.ledger_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                self._seq = entry["seq"]
                self._prev_hash = entry["this_hash"]

    def append(
        self,
        actor: str,
        action: str,
        mode: LedgerMode,
        subject: str,
        inputs_hash: str = "",
        outputs_hash: str = "",
        evidence: list[dict] | None = None,
        approval: ApprovalRef | None = None,
        outcome: LedgerOutcome = LedgerOutcome.OK,
        error: str | None = None,
    ) -> LedgerEntry:
        self._seq += 1
        entry_id = f"{self.run_id}-{self._seq}"
        ts = datetime.now(timezone.utc)

        entry_dict = {
            "seq": self._seq,
            "run_id": self.run_id,
            "entry_id": entry_id,
            "ts": ts.isoformat(),
            "actor": actor,
            "action": action,
            "mode": mode.value,
            "subject": subject,
            "inputs_hash": inputs_hash,
            "outputs_hash": outputs_hash,
            "evidence": evidence or [],
            "approval": approval.model_dump() if approval else None,
            "outcome": outcome.value,
            "error": error,
            "prev_hash": self._prev_hash,
        }

        this_hash = _entry_hash(entry_dict, self._prev_hash)
        entry_dict["this_hash"] = this_hash

        redacted_line = redact(json.dumps(entry_dict, default=str)) + "\n"

        with open(self.ledger_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(redacted_line)
            f.flush()
            os.fsync(f.fileno())

        self._prev_hash = this_hash

        return LedgerEntry(
            seq=self._seq,
            run_id=self.run_id,
            entry_id=entry_id,
            ts=ts,
            actor=actor,
            action=action,
            mode=mode,
            subject=subject,
            inputs_hash=inputs_hash,
            outputs_hash=outputs_hash,
            evidence=evidence or [],
            approval=approval,
            outcome=outcome,
            error=error,
            prev_hash=entry_dict["prev_hash"],
            this_hash=this_hash,
        )
