"""Ledger integrity and changeset endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from groundtruth.api.derive import list_changesets, verify_all_ledgers
from groundtruth.api.schemas import ChangesetItem, LedgerEntry, LedgerIntegrity
from groundtruth.ledger.reader import read_entries


router = APIRouter(prefix="/api", tags=["integrity"])


@router.get("/ledger", response_model=list[LedgerEntry])
def list_ledger_entries(request: Request) -> list[dict]:
    repo = request.app.state.repo
    entries = []
    for ledger_path in repo.all_ledger_paths():
        for entry in read_entries(ledger_path):
            entries.append(
                {
                    "seq": entry.get("seq"),
                    "run_id": entry.get("run_id"),
                    "entry_id": entry.get("entry_id"),
                    "ts": entry.get("ts"),
                    "actor": entry.get("actor", ""),
                    "action": entry.get("action", ""),
                    "mode": entry.get("mode", ""),
                    "subject": entry.get("subject", ""),
                    "outcome": entry.get("outcome", ""),
                    "error": entry.get("error"),
                    "evidence": entry.get("evidence", []),
                }
            )
    entries.sort(key=lambda e: (e.get("ts") or "", e.get("seq") or 0), reverse=True)
    return entries


@router.get("/ledger/integrity", response_model=list[LedgerIntegrity])
def ledger_integrity(request: Request) -> list[dict]:
    repo = request.app.state.repo
    return verify_all_ledgers(repo)


@router.get("/changesets", response_model=list[ChangesetItem])
def changesets(request: Request) -> list[dict]:
    repo = request.app.state.repo
    return list_changesets(repo)
