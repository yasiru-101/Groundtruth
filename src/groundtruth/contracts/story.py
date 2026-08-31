from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StoryStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class DoRFailureCode(str, Enum):
    NO_AC = "NO_AC"
    AC_MALFORMED = "AC_MALFORMED"
    NO_POINTS = "NO_POINTS"
    NO_COMPONENT = "NO_COMPONENT"
    CIRCULAR_DEP = "CIRCULAR_DEP"


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ac_id: str
    given: str = ""
    when: str = ""
    then: str = ""
    raw: str
    is_wellformed: bool = True


class DefinitionOfReadyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    failures: list[str] = Field(default_factory=list)
    checked_at: datetime


class ProvenanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str
    char_span_start: int = 0
    char_span_end: int = 0
    llm_call_id: str = ""


class DedupeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_jira_keys: list[str] = Field(default_factory=list)
    similarity: float = 0.0
    method: str = ""
    threshold: float = 0.0
    human_confirmed: Optional[bool] = None


class Story(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str
    jira_key: Optional[str] = None
    summary: str
    description: str = ""
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    points: Optional[int] = None
    components: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    status: StoryStatus = StoryStatus.DRAFT
    dor: Optional[DefinitionOfReadyResult] = None
    source: Optional[ProvenanceRef] = None
    dedupe: Optional[DedupeVerdict] = None
