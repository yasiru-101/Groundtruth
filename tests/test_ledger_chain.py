"""Tests for the hash-chained ledger.

Chain verification must pass on a clean ledger, then fail after tampering.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from groundtruth.contracts.ledger import LedgerMode, LedgerOutcome
from groundtruth.ledger.reader import (
    ChainVerificationError,
    project_state,
    read_entries,
    verify_chain,
)
from groundtruth.ledger.writer import LedgerWriter


@pytest.fixture()
def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "ledger.jsonl"


@pytest.fixture()
def populated_ledger(ledger_path: Path) -> LedgerWriter:
    writer = LedgerWriter(ledger_path, run_id="test-run-001")
    writer.append(
        actor="steward",
        action="audit",
        mode=LedgerMode.DRY_RUN,
        subject="AUTO-14",
        inputs_hash="abc123",
        outputs_hash="def456",
        evidence=[{"kind": "commit", "ref": "sha1"}],
    )
    writer.append(
        actor="steward",
        action="detect_stale",
        mode=LedgerMode.DRY_RUN,
        subject="AUTO-15",
        outcome=LedgerOutcome.REFUSED,
        error="stale ticket",
    )
    writer.append(
        actor="intake",
        action="create_ticket",
        mode=LedgerMode.PROPOSE,
        subject="AUTO-16",
    )
    return writer


class TestLedgerChain:
    def test_chain_verifies_clean(self, populated_ledger: LedgerWriter, ledger_path: Path) -> None:
        entries = verify_chain(ledger_path)
        assert len(entries) == 3
        assert entries[0]["prev_hash"] == "GENESIS"
        assert entries[1]["prev_hash"] == entries[0]["this_hash"]
        assert entries[2]["prev_hash"] == entries[1]["this_hash"]

    def test_chain_fails_after_tamper(self, populated_ledger: LedgerWriter, ledger_path: Path) -> None:
        verify_chain(ledger_path)

        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[1])
        entry["subject"] = "TAMPERED"
        lines[1] = json.dumps(entry)
        ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

        with pytest.raises(ChainVerificationError) as exc_info:
            verify_chain(ledger_path)
        assert exc_info.value.seq == 2

    def test_seq_increments(self, populated_ledger: LedgerWriter, ledger_path: Path) -> None:
        entries = read_entries(ledger_path)
        seqs = [e["seq"] for e in entries]
        assert seqs == [1, 2, 3]

    def test_genesis_is_first_prev_hash(self, ledger_path: Path) -> None:
        writer = LedgerWriter(ledger_path, run_id="genesis-test")
        writer.append(
            actor="test",
            action="first",
            mode=LedgerMode.DRY_RUN,
            subject="init",
        )
        entries = read_entries(ledger_path)
        assert entries[0]["prev_hash"] == "GENESIS"

    def test_append_preserves_existing_seq(self, ledger_path: Path) -> None:
        writer1 = LedgerWriter(ledger_path, run_id="run1")
        writer1.append(actor="a", action="x", mode=LedgerMode.DRY_RUN, subject="s")
        writer1.append(actor="a", action="y", mode=LedgerMode.DRY_RUN, subject="s")

        writer2 = LedgerWriter(ledger_path, run_id="run2")
        writer2.append(actor="b", action="z", mode=LedgerMode.DRY_RUN, subject="s")

        entries = read_entries(ledger_path)
        assert len(entries) == 3
        assert entries[2]["seq"] == 3

    def test_empty_ledger_verifies(self, ledger_path: Path) -> None:
        ledger_path.write_text("", encoding="utf-8")
        entries = verify_chain(ledger_path)
        assert entries == []


class TestLedgerProjection:
    def test_project_state(self, populated_ledger: LedgerWriter, ledger_path: Path) -> None:
        state = project_state(ledger_path)
        assert state["total_entries"] == 3
        assert state["ok_count"] == 2
        assert state["refused_count"] == 1
        assert "steward" in state["actors"]
        assert "intake" in state["actors"]


class TestRedactionInLedger:
    def test_secrets_redacted_in_ledger(self, ledger_path: Path) -> None:
        writer = LedgerWriter(ledger_path, run_id="redact-test")
        writer.append(
            actor="test",
            action="store_token",
            mode=LedgerMode.DRY_RUN,
            subject="bearer ghp_abcdefghijklmnopqrstuvwxyz1234567890",
        )
        content = ledger_path.read_text(encoding="utf-8")
        assert "ghp_" not in content
        assert "[REDACTED]" in content
