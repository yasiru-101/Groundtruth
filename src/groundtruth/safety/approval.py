from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChangeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    subject: str
    params: dict[str, Any] = Field(default_factory=dict)


class ChangeSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ChangeItem]
    created_at: datetime
    description: str = ""

    def compute_hash(self) -> str:
        raw = self.model_dump_json()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def propose_changeset(
    artifacts_dir: Path,
    items: list[ChangeItem],
    description: str = "",
) -> ChangeSet:
    cs = ChangeSet(
        items=items,
        created_at=datetime.now(timezone.utc),
        description=description,
    )
    cs_hash = cs.compute_hash()

    cs_dir = artifacts_dir / "changesets"
    cs_dir.mkdir(parents=True, exist_ok=True)
    cs_path = cs_dir / f"{cs_hash}.json"
    cs_path.write_text(cs.model_dump_json(indent=2), encoding="utf-8", newline="\n")

    return cs


def load_changeset(artifacts_dir: Path, changeset_hash: str) -> ChangeSet:
    cs_path = artifacts_dir / "changesets" / f"{changeset_hash}.json"
    if not cs_path.exists():
        raise FileNotFoundError(
            f"Changeset with hash '{changeset_hash}' not found at {cs_path}. "
            "Run with --mode propose first."
        )
    data = json.loads(cs_path.read_text(encoding="utf-8"))
    cs = ChangeSet.model_validate(data)
    actual_hash = cs.compute_hash()
    if actual_hash != changeset_hash:
        raise ValueError(
            f"Changeset hash mismatch: expected {changeset_hash}, "
            f"computed {actual_hash}. The changeset may have been tampered with."
        )
    return cs
