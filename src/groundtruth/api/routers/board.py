"""Plan, report, delivery, and traceability endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from groundtruth.api.normalize import format_datetime
from groundtruth.api.schemas import (
    DeliveryItem,
    SprintPlan,
    StandupReport,
    TraceabilityMatrix,
)


router = APIRouter(prefix="/api", tags=["board"])


@router.get("/plan/latest", response_model=SprintPlan)
def latest_plan(request: Request) -> dict:
    repo = request.app.state.repo
    run_dir = repo.latest_run("plan")
    if not run_dir:
        raise HTTPException(status_code=404, detail="no plan run found")
    doc = repo.read_file(run_dir, "plan.json") or {}
    return {
        "run_id": repo.run_id_from_dir(run_dir),
        "run_dir": run_dir.name,
        "project_key": doc.get("project_key", ""),
        "as_of": format_datetime(doc.get("as_of")),
        "velocity": doc.get("velocity", 0),
        "capacity": doc.get("capacity", 0),
        "total_selected_points": doc.get("total_selected_points", 0),
        "total_candidate_points": doc.get("total_candidate_points", 0),
        "over_committed": doc.get("over_committed", False),
        "selected": doc.get("selected", []),
        "unscheduled": doc.get("unscheduled", []),
        "assignments": doc.get("assignments", {}),
        "cycles": doc.get("cycles", []),
    }


@router.get("/report/latest", response_model=StandupReport)
def latest_report(request: Request) -> dict:
    repo = request.app.state.repo
    run_dir = repo.latest_run("report")
    if not run_dir:
        raise HTTPException(status_code=404, detail="no report run found")
    doc = repo.read_file(run_dir, "report.json") or {}
    return {
        "run_id": repo.run_id_from_dir(run_dir),
        "run_dir": run_dir.name,
        "project_key": doc.get("project_key", ""),
        "as_of": format_datetime(doc.get("as_of")) or "",
        "prose": doc.get("prose", ""),
        "markdown": repo.latest_report_markdown(),
        "active_tickets": doc.get("active_tickets", 0),
        "open_discrepancies": doc.get("open_discrepancies", 0),
        "unverified_items": doc.get("unverified_items", 0),
        "stale_items": doc.get("stale_items", 0),
    }


@router.get("/report/markdown")
def latest_report_markdown(request: Request) -> str:
    repo = request.app.state.repo
    text = repo.latest_report_markdown()
    if not text:
        raise HTTPException(status_code=404, detail="no report markdown found")
    return text


@router.get("/delivery/latest", response_model=DeliveryItem)
def latest_delivery(request: Request) -> dict:
    repo = request.app.state.repo
    run_dir = repo.latest_run("deliver")
    if not run_dir:
        raise HTTPException(status_code=404, detail="no delivery run found")
    doc = repo.read_file(run_dir, "delivery_result.json") or {}
    return {
        "run_id": repo.run_id_from_dir(run_dir),
        "run_dir": run_dir.name,
        "ticket_key": doc.get("ticket_key", ""),
        "branch": doc.get("branch", ""),
        "phase": doc.get("phase", ""),
        "green": doc.get("green", False),
        "pr_url": doc.get("pr_url"),
        "head_sha": doc.get("head_sha"),
        "iterations": doc.get("iterations", []),
        "refusals": doc.get("refusals", []),
    }


@router.get("/trace/latest", response_model=TraceabilityMatrix)
def latest_trace(request: Request) -> dict:
    repo = request.app.state.repo
    run_dir = repo.latest_run("deliver")
    if not run_dir:
        raise HTTPException(status_code=404, detail="no delivery run found")
    doc = repo.read_file(run_dir, "trace_manifest.json") or {}
    bindings = []
    for link in doc.get("bindings", []):
        bindings.append(
            {
                "ac_id": link.get("ac_id", ""),
                "test_node_id": link.get("test_node_id", ""),
                "bound_by": link.get("bound_by", ""),
                "bound_at": format_datetime(link.get("bound_at")),
            }
        )
    return {
        "run_id": doc.get("run_id", repo.run_id_from_dir(run_dir)),
        "run_dir": run_dir.name,
        "bindings": bindings,
        "snapshot": doc.get("test_snapshot", {}),
    }
