from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ScoreDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    previous_run_id: Optional[str] = None
    policy_hash: str
    comparable: bool
    dimension_deltas: dict[str, float] = Field(default_factory=dict)
    overall_delta: float = 0.0
    reason: str = ""


class StandupItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    jira_key: str
    summary: str
    status: str
    assignee: Optional[str] = None
    blocked_by: list[str] = Field(default_factory=list)
    discrepancy_count: int = 0
    note: str = ""


class SprintHealth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    velocity_forecast: int = 0
    capacity: int = 0
    over_committed: bool = False
    open_discrepancies: int = 0
    unverified_count: int = 0
    stale_count: int = 0


class ReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health: SprintHealth
    items: list[StandupItem] = Field(default_factory=list)
    delta: Optional[ScoreDelta] = None
    prose: str
    prose_source: str = "template"
