from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.contracts.trace import FailureKind, TraceLink


class DeliveryPhase(str, Enum):
    BRANCH = "branch"
    AUTHOR_TESTS = "author_tests"
    RED_GATE = "red_gate"
    IMPLEMENT = "implement"
    REPAIR = "repair"
    GREEN_GATE = "green_gate"
    RECONCILE = "reconcile"
    COMMIT = "commit"
    PUSH = "push"
    PR = "pr"


class RedGateClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    failed: bool
    failure_kind: Optional[FailureKind] = None
    message_excerpt: str = ""


class RedGateReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    classifications: list[RedGateClassification] = Field(default_factory=list)
    is_valid_red: bool = False


class LockViolationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    path: str
    detail: str
    iteration: int


class RepairIteration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    phase: str
    files_changed: list[str] = Field(default_factory=list)
    red_gate_valid: bool = False
    green: bool = False
    violations: list[LockViolationRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AuthoredTests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_file: str
    bindings: list[TraceLink]
    content: str


class DeliveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_key: str
    branch: str
    phase: DeliveryPhase
    red_gate: RedGateReport
    iterations: list[RepairIteration] = Field(default_factory=list)
    green: bool = False
    pr_url: Optional[str] = None
    draft: bool = False
    head_sha: Optional[str] = None
    refusals: list[str] = Field(default_factory=list)
    unrelated_failures: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    run_dir: str
