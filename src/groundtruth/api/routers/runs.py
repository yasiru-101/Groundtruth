"""Run browsing endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from groundtruth.api.schemas import RunDetail, RunSummary


router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunSummary])
def list_runs(request: Request) -> list[dict]:
    repo = request.app.state.repo
    summaries = []
    for run_dir in repo.run_dirs():
        summaries.append(
            {
                "run_id": repo.run_id_from_dir(run_dir),
                "label": repo.run_label(run_dir),
                "run_dir": run_dir.name,
                "created_at": datetime.fromtimestamp(
                    run_dir.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "files": repo.run_files(run_dir),
            }
        )
    return summaries


@router.get("/{run_id}", response_model=RunDetail)
def get_run(request: Request, run_id: str) -> dict:
    repo = request.app.state.repo
    for run_dir in repo.run_dirs():
        if run_dir.name == run_id:
            files = {}
            for name in repo.run_files(run_dir):
                files[name] = repo.read_file(run_dir, name)
            return {
                "run_id": repo.run_id_from_dir(run_dir),
                "label": repo.run_label(run_dir),
                "run_dir": run_dir.name,
                "created_at": datetime.fromtimestamp(
                    run_dir.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
                "files": files,
            }
    raise HTTPException(status_code=404, detail="run not found")


@router.get("/{run_id}/files/{name}")
def get_run_file(request: Request, run_id: str, name: str) -> dict | str:
    repo = request.app.state.repo
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=404, detail="file not found")
    for run_dir in repo.run_dirs():
        if run_dir.name == run_id:
            try:
                content = repo.read_file(run_dir, name)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if content is None:
                raise HTTPException(status_code=404, detail="file not found")
            return content
    raise HTTPException(status_code=404, detail="run not found")
