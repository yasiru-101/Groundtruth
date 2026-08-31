from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceKind(str, Enum):
    COMMIT = "commit"
    PR = "pr"
    CHECK_RUN = "check_run"
    JIRA_CHANGELOG = "jira_changelog"
    TEST_RESULT = "test_result"
    BRANCH = "branch"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EvidenceKind
    ref: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    observed_at: datetime
    detail: dict[str, str] = Field(default_factory=dict)
