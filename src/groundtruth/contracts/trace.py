from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TraceMatrixStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    MISSING = "missing"
    ERROR = "error"
    SKIPPED = "skipped"
    NOT_COLLECTED = "not_collected"


class FailureKind(str, Enum):
    ASSERTION = "assertion"
    IMPORT_ERROR = "import_error"
    COLLECTION_ERROR = "collection_error"


class TraceLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ac_id: str
    test_node_id: str
    bound_by: str = "manifest"
    bound_at: datetime
    test_file_hash: str


class RedProof(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    failed_at: datetime
    failure_kind: FailureKind
    longrepr_excerpt: str = ""


class TraceMatrixRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ac_id: str
    ac_text: str
    test_node_ids: list[str] = Field(default_factory=list)
    status: TraceMatrixStatus
    red_proof: Optional[RedProof] = None
    evidence: list[dict] = Field(default_factory=list)
