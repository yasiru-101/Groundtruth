"""Background job endpoints for re-running audit/score/report."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from groundtruth.api.schemas import JobStatus


class JobCommand(BaseModel):
    command: str


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobStatus)
def submit_job(payload: JobCommand, request: Request) -> dict:
    store = request.app.state.job_store
    try:
        job_id = store.submit(payload.command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = store.get(job_id)
    return {
        "job_id": job.job_id,
        "command": job.command,
        "status": job.status,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "result": job.result,
        "error": job.error,
    }


@router.get("/{job_id}", response_model=JobStatus)
def get_job(job_id: str, request: Request) -> dict:
    job = request.app.state.job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.job_id,
        "command": job.command,
        "status": job.status,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "result": job.result,
        "error": job.error,
    }
