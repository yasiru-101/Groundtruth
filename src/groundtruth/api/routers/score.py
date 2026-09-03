"""Score endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from groundtruth.api.derive import build_score_history, compare_score_runs
from groundtruth.api.schemas import ScoreHistoryPoint, ScoreLatest


router = APIRouter(prefix="/api/score", tags=["score"])


def _latest_score_doc(repo) -> tuple:
    run_dir = repo.latest_run("score")
    if not run_dir:
        raise HTTPException(status_code=404, detail="no score run found")
    doc = repo.read_file(run_dir, "score.json") or {}
    if not doc:
        raise HTTPException(status_code=404, detail="score.json empty")
    return run_dir, doc


@router.get("/latest", response_model=ScoreLatest)
def latest_score(request: Request) -> dict:
    from groundtruth.api.normalize import format_datetime

    repo = request.app.state.repo
    run_dir, doc = _latest_score_doc(repo)
    score = doc.get("score", {})

    dimensions = []
    for dim in score.get("dimensions", []):
        dimensions.append(
            {
                "name": dim.get("name", ""),
                "value": dim.get("value"),
                "weight": dim.get("weight", 0.0),
                "raw": dim.get("raw", ""),
                "evidence": dim.get("evidence", []),
            }
        )

    return {
        "run_id": score.get("run_id", repo.run_id_from_dir(run_dir)),
        "run_dir": run_dir.name,
        "project_key": score.get("project_key", ""),
        "as_of": format_datetime(score.get("as_of")),
        "total": float(score.get("total", 0.0)),
        "policy_hash": score.get("policy_hash", ""),
        "board_snapshot_hash": score.get("board_snapshot_hash", ""),
        "dimensions": dimensions,
        "control_group": doc.get("control_group"),
    }


@router.get("/history", response_model=list[ScoreHistoryPoint])
def score_history(request: Request) -> list[dict]:
    repo = request.app.state.repo
    return build_score_history(repo)


@router.get("/compare")
def compare_score(request: Request, before: str, after: str) -> dict:
    repo = request.app.state.repo
    try:
        return compare_score_runs(repo, before, after)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
