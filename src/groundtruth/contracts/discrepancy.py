from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .evidence import Evidence


class DiscrepancySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DiscrepancyType(str, Enum):
    STALE_IN_PROGRESS = "STALE_IN_PROGRESS"
    MERGED_PR_TICKET_OPEN = "MERGED_PR_TICKET_OPEN"
    ORPHAN_BRANCH = "ORPHAN_BRANCH"
    UNVERIFIED_NO_MAPPING = "UNVERIFIED_NO_MAPPING"
    UNVERIFIED_MAPPING_STALE = "UNVERIFIED_MAPPING_STALE"
    UNVERIFIED_TEST_FAILING = "UNVERIFIED_TEST_FAILING"
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"


class ActionVerb(str, Enum):
    TRANSITION = "TRANSITION"
    COMMENT = "COMMENT"
    LINK = "LINK"
    CREATE_TICKET = "CREATE_TICKET"
    CLOSE_DUPLICATE = "CLOSE_DUPLICATE"
    NONE = "NONE"


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verb: ActionVerb
    target: str = ""
    params: dict[str, str] = Field(default_factory=dict)
    reversible: bool = True
    requires_approval: bool = True


class Discrepancy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discrepancy_id: str
    type: DiscrepancyType
    severity: DiscrepancySeverity
    subject: str
    evidence: list[Evidence] = Field(..., min_length=1)
    proposed_action: ProposedAction
    detected_at: datetime
    as_of: datetime
    detector_version: str = "0.1.0"

    @field_validator("evidence")
    @classmethod
    def _evidence_must_be_non_empty(cls, v: list[Evidence]) -> list[Evidence]:
        if not v:
            raise ValueError(
                "A discrepancy must cite at least one piece of evidence. "
                "A claim without proof cannot be constructed."
            )
        return v

    @classmethod
    def build(
        cls,
        type: DiscrepancyType,
        severity: DiscrepancySeverity,
        subject: str,
        evidence: list[Evidence],
        proposed_action: ProposedAction,
        detected_at: datetime,
        as_of: datetime,
        detector_version: str = "0.1.0",
    ) -> Discrepancy:
        from groundtruth.ids import discrepancy_id

        did = discrepancy_id(
            type.value,
            subject,
            [e.ref for e in evidence],
        )
        return cls(
            discrepancy_id=did,
            type=type,
            severity=severity,
            subject=subject,
            evidence=evidence,
            proposed_action=proposed_action,
            detected_at=detected_at,
            as_of=as_of,
            detector_version=detector_version,
        )
