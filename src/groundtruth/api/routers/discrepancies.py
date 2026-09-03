"""Discrepancy inbox endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from groundtruth.api.schemas import DiscrepancyItem


router = APIRouter(prefix="/api/discrepancies", tags=["discrepancies"])


def _latest_discrepancies(repo):
    doc = repo.latest_discrepancies()
    if not doc:
        raise HTTPException(status_code=404, detail="no audit run found")
    return doc


@router.get("", response_model=list[DiscrepancyItem])
def list_discrepancies(
    request: Request,
    severity: str | None = Query(None),
    dtype: str | None = Query(None, alias="type"),
    subject: str | None = Query(None),
) -> list[dict]:
    repo = request.app.state.repo
    doc = _latest_discrepancies(repo)
    items = doc.get("discrepancies", [])
    filtered = []
    for item in items:
        if severity and item.get("severity") != severity:
            continue
        if dtype and item.get("type") != dtype:
            continue
        if subject and subject.lower() not in item.get("subject", "").lower():
            continue
        filtered.append(item)
    return filtered


@router.get("/{discrepancy_id}", response_model=DiscrepancyItem)
def get_discrepancy(request: Request, discrepancy_id: str) -> dict:
    repo = request.app.state.repo
    doc = _latest_discrepancies(repo)
    for item in doc.get("discrepancies", []):
        if item.get("discrepancy_id") == discrepancy_id:
            return item
    raise HTTPException(status_code=404, detail="discrepancy not found")
