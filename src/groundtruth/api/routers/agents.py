"""Agent activity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from groundtruth.api.derive import build_activity_feed, build_agent_summary
from groundtruth.api.schemas import AgentSummary


router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/summary", response_model=AgentSummary)
def agent_summary(request: Request) -> dict:
    repo = request.app.state.repo
    return build_agent_summary(repo)


@router.get("/activity")
def agent_activity(request: Request) -> list[dict]:
    repo = request.app.state.repo
    return build_activity_feed(repo)
