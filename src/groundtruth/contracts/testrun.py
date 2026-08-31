from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TestOutcomeStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    NOT_COLLECTED = "not_collected"


class TestOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    status: TestOutcomeStatus
    duration: float = 0.0
    message: str = ""


class TestRunResult(BaseModel):
    __test__ = False
    model_config = ConfigDict(extra="forbid")

    run_id: str
    exit_code: int
    tests: dict[str, TestOutcome] = Field(default_factory=dict)
    collected_node_ids: set[str] = Field(default_factory=set)
    raw_report_path: str = ""
