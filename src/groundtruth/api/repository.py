"""Read-only artifact repository for the dashboard API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from groundtruth.api.normalize import format_datetime, normalize_payload, safe_read_json


class ArtifactRepository:
    """Scan run directories and safely load their JSON/text files."""

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = Path(artifacts_dir).resolve()

    def run_dirs(self) -> list[Path]:
        """Return sorted run directories (newest timestamp first)."""
        if not self.artifacts_dir.exists():
            return []
        dirs = [
            p
            for p in self.artifacts_dir.iterdir()
            if p.is_dir() and p.name.startswith("run_")
        ]
        return sorted(dirs, reverse=True)

    def latest_run(self, label: str) -> Path | None:
        """Return the most recent run directory matching a label suffix."""
        for run_dir in self.run_dirs():
            if run_dir.name.endswith(f"_{label}"):
                return run_dir
        return None

    def run_label(self, run_dir: Path) -> str:
        """Extract the label from a run directory name."""
        name = run_dir.name
        if name.startswith("run_") and "_" in name[4:]:
            return name.rsplit("_", 1)[1]
        return name

    def run_id_from_dir(self, run_dir: Path) -> str:
        """Best-effort run_id: prefer ledger, then directory name."""
        ledger = run_dir / "ledger.jsonl"
        if ledger.exists():
            try:
                first = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
                return first.get("run_id", run_dir.name)
            except Exception:
                pass
        return run_dir.name

    def run_files(self, run_dir: Path) -> list[str]:
        """List JSON/text files in a run directory."""
        if not run_dir.exists():
            return []
        return sorted(
            p.name
            for p in run_dir.iterdir()
            if p.is_file() and p.suffix in {".json", ".md", ".jsonl", ".txt"}
        )

    def read_file(self, run_dir: Path, name: str) -> Any:
        """Safely read a file from a run directory; reject path traversal."""
        target = (run_dir / name).resolve()
        if not str(target).startswith(str(run_dir.resolve())):
            raise ValueError("path traversal rejected")
        if not target.exists() or not target.is_file():
            return None
        if target.suffix == ".md" or target.name.endswith(".jsonl"):
            return target.read_text(encoding="utf-8")
        return normalize_payload(safe_read_json(target))

    def latest_discrepancies(self) -> dict[str, Any]:
        run_dir = self.latest_run("audit")
        if not run_dir:
            return {}
        return self.read_file(run_dir, "discrepancies.json") or {}

    def latest_score(self) -> dict[str, Any]:
        run_dir = self.latest_run("score")
        if not run_dir:
            return {}
        return self.read_file(run_dir, "score.json") or {}

    def latest_report(self) -> dict[str, Any]:
        run_dir = self.latest_run("report")
        if not run_dir:
            return {}
        return self.read_file(run_dir, "report.json") or {}

    def latest_report_markdown(self) -> str:
        run_dir = self.latest_run("report")
        if not run_dir:
            return ""
        text = self.read_file(run_dir, "report.md")
        return text if isinstance(text, str) else ""

    def latest_plan(self) -> dict[str, Any]:
        run_dir = self.latest_run("plan")
        if not run_dir:
            return {}
        return self.read_file(run_dir, "plan.json") or {}

    def latest_delivery(self) -> dict[str, Any]:
        run_dir = self.latest_run("deliver")
        if not run_dir:
            return {}
        return self.read_file(run_dir, "delivery_result.json") or {}

    def latest_trace_manifest(self) -> dict[str, Any]:
        run_dir = self.latest_run("deliver")
        if not run_dir:
            return {}
        return self.read_file(run_dir, "trace_manifest.json") or {}

    def all_score_runs(self) -> list[tuple[Path, dict[str, Any]]]:
        """Return (run_dir, score_doc) for every score run, newest first."""
        results: list[tuple[Path, dict[str, Any]]] = []
        for run_dir in self.run_dirs():
            if not run_dir.name.endswith("_score"):
                continue
            doc = self.read_file(run_dir, "score.json") or {}
            if doc:
                results.append((run_dir, doc))
        return results

    def all_audit_runs(self) -> list[tuple[Path, dict[str, Any]]]:
        results: list[tuple[Path, dict[str, Any]]] = []
        for run_dir in self.run_dirs():
            if not run_dir.name.endswith("_audit"):
                continue
            doc = self.read_file(run_dir, "discrepancies.json") or {}
            if doc:
                results.append((run_dir, doc))
        return results

    def all_ledger_paths(self) -> list[Path]:
        return sorted(self.artifacts_dir.glob("run_*/ledger.jsonl"))
