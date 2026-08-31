from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LedgerOutcome(str, Enum):
    OK = "ok"
    REFUSED = "refused"
    ERROR = "error"


class LedgerMode(str, Enum):
    PROPOSE = "PROPOSE"
    APPLY = "APPLY"
    DRY_RUN = "DRY_RUN"
    REPLAY = "REPLAY"


class ApprovalRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    changeset_hash: str
    approved_by: str
    approved_at: datetime


class LedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    run_id: str
    entry_id: str
    ts: datetime
    actor: str
    action: str
    mode: LedgerMode
    subject: str
    inputs_hash: str
    outputs_hash: str
    evidence: list[dict] = Field(default_factory=list)
    approval: Optional[ApprovalRef] = None
    outcome: LedgerOutcome
    error: Optional[str] = None
    prev_hash: str
    this_hash: str = ""
