from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .evidence import Evidence


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: Optional[float] = None
    numerator: int = 0
    denominator: int = 0
    weight: float = 1.0
    evidence: list[Evidence] = Field(default_factory=list)
    excluded_reason: Optional[str] = None


class TruthfulnessScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: float
    dimensions: list[DimensionScore]
    policy_version: str
    policy_hash: str
    as_of: datetime
    board_snapshot_hash: str
    control_group: Optional[float] = None
    evidence_log_path: str = ""
