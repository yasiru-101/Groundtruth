"""Sprint plan contract: the deterministic output of the PlannerAgent."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PlannedTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    summary: str = ""
    points: int
    components: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    assignee: Optional[str] = None


class SprintPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_key: str
    as_of: datetime
    velocity: int
    capacity: int
    total_candidate_points: int
    total_selected_points: int
    over_committed: bool
    cycles: list[list[str]] = Field(default_factory=list)
    selected: list[PlannedTicket] = Field(default_factory=list)
    unscheduled: list[PlannedTicket] = Field(default_factory=list)
    assignments: dict[str, list[str]] = Field(default_factory=dict)
