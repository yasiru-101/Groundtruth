"""Manifest readers: the seed manifest (Phase 2) and the trace manifest.

Read + validate only. The trace manifest is WRITTEN by Phase 5 Delivery; its
reader and on-disk format are frozen here so Phase 5 cannot invent a shape
that Phase 3 scoring was never tested against.

Seed manifest (artifacts/run_*_seed/manifest.json):
    scenario_version, project_key, run_id, seeded_at,
    tickets: [{hint, key, summary, status, control, branch}],
    git: {base_branch, repo_initialized, base_tip,
          branches: [{hint, key, branch, created, pushed, pr, commits}]}

Trace manifest (artifacts/run_*_deliver/trace_manifest.json):
    trace_version, run_id, created_at,
    bindings: [{ac_id, test_node_id, bound_by, bound_at, test_file_hash}],
    test_snapshot: {ran_at, collected_node_ids, outcomes: {node_id: status}}
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from groundtruth.contracts.board import TraceSnapshot
from groundtruth.contracts.trace import TraceLink

SEED_MANIFEST_NAME = "manifest.json"
TRACE_MANIFEST_NAME = "trace_manifest.json"

_ALLOWED_TEST_STATUSES = frozenset(
    {"passed", "failed", "skipped", "error", "not_collected"}
)


class ManifestError(Exception):
    pass


# -- seed manifest ---------------------------------------------------------


class SeedBranch(BaseModel):
    model_config = ConfigDict(extra="allow")

    hint: str
    key: str
    branch: str


class SeedTicket(BaseModel):
    """One seeded ticket. The raw ``branch`` value is the scenario spec dict
    (name_template + commits); resolved branch names live in ``git.branches``."""

    model_config = ConfigDict(extra="allow")

    hint: str
    key: str
    summary: str
    status: str = ""
    control: bool = False


class SeedGit(BaseModel):
    model_config = ConfigDict(extra="allow")

    base_branch: str = "main"
    repo_initialized: bool = False
    base_tip: str | None = None
    branches: list[SeedBranch] = Field(default_factory=list)


class SeedManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    scenario_version: int
    project_key: str
    run_id: str
    seeded_at: datetime
    tickets: list[SeedTicket]
    git: SeedGit = Field(default_factory=SeedGit)

    @field_validator("tickets")
    @classmethod
    def _tickets_non_empty(cls, v: list[SeedTicket]) -> list[SeedTicket]:
        if not v:
            raise ValueError("seed manifest must list at least one ticket")
        return v

    def branch_for_key(self, key: str) -> str:
        for entry in self.git.branches:
            if entry.key == key:
                return entry.branch
        return ""


def _validate_seed_doc(doc: dict) -> None:
    keys = {"scenario_version", "project_key", "run_id", "seeded_at", "tickets"}
    missing = keys - set(doc)
    if missing:
        raise ManifestError(f"seed manifest missing keys: {sorted(missing)}")
    seen: set[str] = set()
    for ticket in doc["tickets"]:
        for field in ("hint", "key", "summary"):
            if not ticket.get(field):
                raise ManifestError(f"seed manifest ticket missing {field!r}: {ticket}")
        if ticket["key"] in seen:
            raise ManifestError(f"seed manifest has duplicate key {ticket['key']!r}")
        seen.add(ticket["key"])
    if doc.get("project_key") and not doc["tickets"][0]["key"].startswith(
        f"{doc['project_key']}-"
    ):
        raise ManifestError(
            f"seed manifest project {doc['project_key']!r} does not match "
            f"ticket keys like {doc['tickets'][0]['key']!r}"
        )


def load_seed_manifest(path: Path) -> SeedManifest:
    import json

    if not path.exists():
        raise ManifestError(f"seed manifest not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ManifestError(f"seed manifest unreadable at {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError(f"seed manifest at {path} is not a JSON object.")
    _validate_seed_doc(doc)
    try:
        return SeedManifest.model_validate(doc)
    except Exception as exc:
        raise ManifestError(f"seed manifest at {path} failed validation: {exc}") from exc


def latest_seed_manifest(artifacts_dir: Path) -> SeedManifest | None:
    candidates = sorted(artifacts_dir.glob(f"run_*/{SEED_MANIFEST_NAME}"))
    for path in reversed(candidates):
        try:
            return load_seed_manifest(path)
        except ManifestError:
            continue
    return None


# -- trace manifest --------------------------------------------------------


class TestSnapshotDoc(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ran_at: datetime | None = None
    collected_node_ids: list[str] = Field(default_factory=list)
    outcomes: dict[str, str] = Field(default_factory=dict)

    @field_validator("outcomes")
    @classmethod
    def _outcomes_known(cls, v: dict[str, str]) -> dict[str, str]:
        unknown = {status for status in v.values() if status not in _ALLOWED_TEST_STATUSES}
        if unknown:
            raise ValueError(f"unknown test outcome values: {sorted(unknown)}")
        return v


class TraceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_version: str
    run_id: str
    created_at: datetime
    bindings: list[TraceLink] = Field(default_factory=list)
    test_snapshot: TestSnapshotDoc = Field(default_factory=TestSnapshotDoc)

    @field_validator("bindings")
    @classmethod
    def _bindings_wellformed(cls, v: list[TraceLink]) -> list[TraceLink]:
        seen: set[tuple[str, str]] = set()
        for link in v:
            if "#" not in link.ac_id:
                raise ValueError(
                    f"ac_id must be '<JIRA-KEY>#<n>', got {link.ac_id!r}"
                )
            if not link.test_node_id:
                raise ValueError("test_node_id must be non-empty")
            pair = (link.ac_id, link.test_node_id)
            if pair in seen:
                raise ValueError(f"duplicate binding {pair}")
            seen.add(pair)
        return v

    def snapshot(self) -> TraceSnapshot:
        outcomes = self.test_snapshot.outcomes
        return TraceSnapshot(
            bindings=list(self.bindings),
            collected_node_ids=list(self.test_snapshot.collected_node_ids),
            failing_node_ids=[
                node
                for node, status in sorted(outcomes.items())
                if status in {"failed", "error"}
            ],
            ran_at=self.test_snapshot.ran_at,
        )


def _validate_trace_doc(doc: dict) -> None:
    keys = {"trace_version", "run_id", "created_at"}
    missing = keys - set(doc)
    if missing:
        raise ManifestError(f"trace manifest missing keys: {sorted(missing)}")


def load_trace_manifest(path: Path) -> TraceManifest:
    import json

    if not path.exists():
        raise ManifestError(f"trace manifest not found: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ManifestError(f"trace manifest unreadable at {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError(f"trace manifest at {path} is not a JSON object.")
    _validate_trace_doc(doc)
    try:
        return TraceManifest.model_validate(doc)
    except Exception as exc:
        raise ManifestError(f"trace manifest at {path} failed validation: {exc}") from exc


def latest_trace_manifest(artifacts_dir: Path) -> TraceManifest | None:
    candidates = sorted(artifacts_dir.glob(f"run_*/{TRACE_MANIFEST_NAME}"))
    for path in reversed(candidates):
        try:
            return load_trace_manifest(path)
        except ManifestError:
            continue
    return None
