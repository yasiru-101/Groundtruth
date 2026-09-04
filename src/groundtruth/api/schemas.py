"""Response schemas for the Groundtruth dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    demo_mode: bool
    artifacts_dir: str


class PolicyResponse(BaseModel):
    policy_hash: str
    policy_date: str
    policy_path: str


class DemoResponse(BaseModel):
    project_key: str
    run_count: int
    as_of: Optional[str] = None


class RunSummary(BaseModel):
    run_id: str
    label: str
    run_dir: str
    created_at: str
    files: list[str]


class RunDetail(BaseModel):
    run_id: str
    label: str
    run_dir: str
    created_at: str
    files: dict[str, Any]


class ScoreDimension(BaseModel):
    name: str
    value: Optional[float]
    weight: float
    raw: str
    evidence: list[dict] = Field(default_factory=list)


class ScoreLatest(BaseModel):
    run_id: str
    run_dir: str
    project_key: str
    as_of: str
    total: float
    policy_hash: str
    board_snapshot_hash: str
    dimensions: list[ScoreDimension]
    control_group: Optional[dict] = None


class ScoreHistoryPoint(BaseModel):
    run_id: str
    run_dir: str
    as_of: str
    total: float
    policy_hash: str


class ScoreCompare(BaseModel):
    before: ScoreHistoryPoint
    after: ScoreHistoryPoint
    delta: float
    dimensions_changed: list[dict]
    resolved: list[str]
    introduced: list[str]


class DiscrepancyEvidence(BaseModel):
    kind: str
    ref: str
    url: str
    observed_at: Optional[str] = None
    detail: dict = Field(default_factory=dict)


class ProposedAction(BaseModel):
    verb: str
    target: str
    params: dict = Field(default_factory=dict)
    reversible: bool
    requires_approval: bool


class DiscrepancyItem(BaseModel):
    discrepancy_id: str
    type: str
    severity: str
    subject: str
    evidence: list[DiscrepancyEvidence]
    proposed_action: ProposedAction
    detected_at: Optional[str] = None
    as_of: Optional[str] = None
    detector_version: Optional[str] = None


class PlanTicket(BaseModel):
    key: str
    summary: str
    points: int
    assignee: Optional[str] = None
    depends_on: list[str] = Field(default_factory=list)


class SprintPlan(BaseModel):
    run_id: str
    run_dir: str
    project_key: str
    as_of: str
    velocity: int
    capacity: int
    total_selected_points: int
    total_candidate_points: int
    over_committed: bool
    selected: list[PlanTicket]
    unscheduled: list[PlanTicket]
    assignments: dict[str, list[str]] = Field(default_factory=dict)
    cycles: list[list[str]] = Field(default_factory=list)


class StandupReport(BaseModel):
    run_id: str
    run_dir: str
    project_key: str
    as_of: str
    prose: str
    markdown: str
    active_tickets: int
    open_discrepancies: int
    unverified_items: int
    stale_items: int


class DeliveryItem(BaseModel):
    run_id: str
    run_dir: str
    ticket_key: str
    branch: str
    phase: str
    green: bool
    pr_url: Optional[str] = None
    head_sha: Optional[str] = None
    iterations: list[dict] = Field(default_factory=list)
    refusals: list[str] = Field(default_factory=list)


class TraceBinding(BaseModel):
    ac_id: str
    test_node_id: str
    bound_by: str
    bound_at: Optional[str] = None


class TraceabilityMatrix(BaseModel):
    run_id: str
    run_dir: str
    bindings: list[TraceBinding]
    snapshot: dict = Field(default_factory=dict)


class LedgerEntry(BaseModel):
    seq: int
    run_id: str
    entry_id: str
    ts: str
    actor: str
    action: str
    mode: str
    subject: str
    outcome: str
    error: Optional[str] = None
    evidence: list[dict] = Field(default_factory=list)


class LedgerIntegrity(BaseModel):
    run_dir: str
    ledger_path: str
    valid: bool
    entries: int
    error: Optional[str] = None


class ChangesetItem(BaseModel):
    hash: str
    description: str
    items: list[dict] = Field(default_factory=list)


class AgentActivity(BaseModel):
    actor: str
    action_count: int
    last_action: Optional[str] = None
    last_subject: Optional[str] = None
    last_ts: Optional[str] = None


class AgentSummary(BaseModel):
    actors: list[AgentActivity]
    total_actions: int
    refusals: int


class JobStatus(BaseModel):
    job_id: str
    command: str
    status: str  # pending, running, completed, failed
    created_at: str
    finished_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class GitHubConnectionStatus(BaseModel):
    connected: bool
    auth_kind: str = ""
    repo_slug: str = ""
    login: str = ""
    scopes: list[str] = Field(default_factory=list)
    oauth_available: bool = False


class JiraConnectionStatus(BaseModel):
    connected: bool
    auth_kind: str = ""
    site_url: str = ""
    project_key: str = ""
    email: str = ""
    oauth_available: bool = False


class LlmConnectionStatus(BaseModel):
    connected: bool
    provider: str = ""
    base_url: str = ""
    model: str = ""
    key_last4: str = ""


class ConnectionsStatus(BaseModel):
    github: GitHubConnectionStatus
    jira: JiraConnectionStatus
    llm: LlmConnectionStatus


class ParsedUrlResponse(BaseModel):
    provider: str
    valid: bool
    owner: str = ""
    name: str = ""
    base_url: str = ""
    project_key: str = ""


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str = ""


class OAuthStartResponse(BaseModel):
    authorize_url: str
