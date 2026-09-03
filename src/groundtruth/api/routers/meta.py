"""Meta endpoints: health, policy, demo."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request

from groundtruth.api.normalize import format_datetime
from groundtruth.api.schemas import DemoResponse, HealthResponse, PolicyResponse
from groundtruth.scoring.policy import POLICY_PATH, load_policy


router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "demo_mode": settings.demo_mode,
        "artifacts_dir": str(settings.artifacts_dir),
    }


@router.get("/policy", response_model=PolicyResponse)
def policy(request: Request) -> dict:
    repo = request.app.state.repo
    try:
        policy_doc = load_policy(POLICY_PATH)
        policy_path = POLICY_PATH
    except Exception:
        return {
            "policy_hash": "",
            "policy_date": "",
            "policy_path": str(POLICY_PATH),
        }
    policy_mtime = datetime.fromtimestamp(policy_path.stat().st_mtime, tz=timezone.utc)
    return {
        "policy_hash": policy_doc.policy_hash,
        "policy_date": format_datetime(policy_mtime) or "",
        "policy_path": str(policy_path),
    }


@router.get("/demo", response_model=DemoResponse)
def demo(request: Request) -> dict:
    repo = request.app.state.repo
    run_dirs = repo.run_dirs()
    latest_audit = repo.latest_discrepancies()
    return {
        "project_key": latest_audit.get("project_key", ""),
        "run_count": len(run_dirs),
        "as_of": format_datetime(latest_audit.get("as_of")),
    }
