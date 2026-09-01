"""Board + repo snapshots: the inputs every Phase 3 detector consumes.

``BoardState`` is what Jira claims; ``RepoState`` is what git/GitHub can
prove. Detectors are pure functions over the pair plus a clock — no I/O
anywhere in this package, so every rule is golden-fixture testable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.contracts.story import AcceptanceCriterion
from groundtruth.contracts.trace import TraceLink

TERMINAL_DISPOSITION_STATUSES = frozenset(
    {"done", "resolved", "closed", "cancelled", "won't do", "wont do"}
)


def is_done(ticket: BoardTicket) -> bool:
    return ticket.status.strip().lower() in {"done", "resolved"}


def is_active(ticket: BoardTicket) -> bool:
    return ticket.status.strip().lower() not in TERMINAL_DISPOSITION_STATUSES


def is_in_progress(ticket: BoardTicket) -> bool:
    return ticket.status.strip().lower() == "in progress"


class BoardTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    summary: str
    description: str = ""
    status: str = ""
    labels: list[str] = Field(default_factory=list)
    points: Optional[int] = None
    components: list[str] = Field(default_factory=list)
    branch: Optional[str] = None
    is_control: bool = False
    status_changed_at: Optional[datetime] = None
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)


class TraceSnapshot(BaseModel):
    """AC->test bindings plus the last test run they must survive."""

    model_config = ConfigDict(extra="forbid")

    bindings: list[TraceLink] = Field(default_factory=list)
    collected_node_ids: list[str] = Field(default_factory=list)
    failing_node_ids: list[str] = Field(default_factory=list)
    ran_at: Optional[datetime] = None

    def binding_for(self, ac_id: str) -> TraceLink | None:
        for link in self.bindings:
            if link.ac_id == ac_id:
                return link
        return None

    def bindings_for_ticket(self, jira_key: str) -> list[TraceLink]:
        prefix = f"{jira_key}#"
        return [l for l in self.bindings if l.ac_id.startswith(prefix)]


class BoardState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_key: str
    tickets: list[BoardTicket] = Field(default_factory=list)
    ghosts: list[GhostTicket] = Field(default_factory=list)
    trace: Optional[TraceSnapshot] = None
    as_of: datetime
    jira_base_url: str = ""

    def ticket(self, key: str) -> BoardTicket | None:
        for ticket in self.tickets:
            if ticket.key == key:
                return ticket
        return None

    def ticket_for_branch(self, branch: str) -> BoardTicket | None:
        for ticket in self.tickets:
            if ticket.branch == branch:
                return ticket
        lowered = branch.lower()
        for ticket in self.tickets:
            if ticket.branch and ticket.branch.lower() == lowered:
                return ticket
        for ticket in self.tickets:
            if ticket.key.lower() in lowered.split("/"):
                return ticket
        return None

    def jira_url(self, key: str) -> str:
        if self.jira_base_url:
            return f"{self.jira_base_url.rstrip('/')}/browse/{key}"
        return key


class GhostTicket(BaseModel):
    """A ticket the seed manifest says existed but the board no longer shows.

    Deleting a ticket deletes its evidence, not its history: ghosts stay in
    the staleness budget at full penalty and, if they claimed In Progress,
    count against progress_integrity. You cannot delete your way to honesty.
    """

    model_config = ConfigDict(extra="forbid")

    key: str
    status: str = ""
    is_control: bool = False


class RepoCommit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha: str
    author_date: datetime
    subject: str = ""
    author_name: str = ""


class RepoBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    commits: list[RepoCommit] = Field(default_factory=list)  # newest first

    @property
    def tip(self) -> RepoCommit | None:
        return self.commits[0] if self.commits else None


class RepoPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    state: str  # OPEN / MERGED / CLOSED
    head_ref: str
    base_ref: str
    merged_at: Optional[datetime] = None
    merge_sha: Optional[str] = None  # commit that landed on the base branch
    url: str = ""

    @property
    def is_merged(self) -> bool:
        return self.state.upper() == "MERGED" or self.merged_at is not None


class RepoCheckRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str  # the commit the check ran on
    name: str
    conclusion: str  # success / failure / ...

    @property
    def passed(self) -> bool:
        return self.conclusion.strip().lower() == "success"


class RepoState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_branch: str = "main"
    branches: list[RepoBranch] = Field(default_factory=list)
    pull_requests: list[RepoPullRequest] = Field(default_factory=list)
    check_runs: list[RepoCheckRun] = Field(default_factory=list)
    repo_url: str = ""

    def branch(self, name: str) -> RepoBranch | None:
        for branch in self.branches:
            if branch.name == name:
                return branch
        return None

    def merged_pr_for_head(self, head_ref: str) -> RepoPullRequest | None:
        for pr in self.pull_requests:
            if pr.head_ref == head_ref and pr.is_merged:
                return pr
        return None

    def check_runs_for(self, ref: str) -> list[RepoCheckRun]:
        return [run for run in self.check_runs if run.ref == ref]

    def commit_url(self, sha: str) -> str:
        if self.repo_url:
            return f"{self.repo_url.rstrip('/')}/commit/{sha}"
        return sha

    def branch_url(self, name: str) -> str:
        if self.repo_url:
            return f"{self.repo_url.rstrip('/')}/tree/{name}"
        return name
