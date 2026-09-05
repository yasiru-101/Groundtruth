"""Background job runner for re-running audit/score/report in replay mode."""

from __future__ import annotations

import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from groundtruth.api.settings import ApiSettings


class Job:
    def __init__(self, job_id: str, command: str, artifacts_dir: Path, fixtures_dir: Path | None = None) -> None:
        self.job_id = job_id
        self.command = command
        self.artifacts_dir = artifacts_dir
        self.fixtures_dir = fixtures_dir
        self.status = "pending"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: str | None = None
        self.result: dict[str, Any] | None = None
        self.error: str | None = None

    def run(self) -> None:
        self.status = "running"
        env = {
            **dict(__import__("os").environ),
            "GT_ARTIFACTS_DIR": str(self.artifacts_dir),
        }
        if self.fixtures_dir:
            env["GT_FIXTURES_DIR"] = str(self.fixtures_dir)
        cmd = [
            __import__("sys").executable,
            "-m",
            "groundtruth",
            "--run-mode",
            "replay",
            self.command,
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=Path(__file__).resolve().parent.parent.parent.parent,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                self.status = "failed"
                self.error = (proc.stderr or proc.stdout or "unknown error")[:2000]
            else:
                self.status = "completed"
                # Extract the run directory from the last line of stdout.
                last_line = proc.stdout.strip().splitlines()[-1]
                run_dir = ""
                if ": " in last_line:
                    run_dir = last_line.split(": ", 1)[1].strip()
                self.result = {
                    "stdout": proc.stdout[-4000:],
                    "run_dir": run_dir,
                }
        except subprocess.TimeoutExpired:
            self.status = "failed"
            self.error = "timeout"
        except Exception as exc:
            self.status = "failed"
            self.error = str(exc)
        finally:
            self.finished_at = datetime.now(timezone.utc).isoformat()


class JobStore:
    """In-memory job store. Jobs are lost on server restart by design."""

    def __init__(self, settings: ApiSettings) -> None:
        self.artifacts_dir = settings.artifacts_dir
        self.fixtures_dir = settings.fixtures_dir
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._jobs: dict[str, Job] = {}

    def submit(self, command: str) -> str:
        if command not in {"audit", "score", "report"}:
            raise ValueError(f"command not allowed: {command}")
        job_id = str(uuid.uuid4())
        job = Job(job_id, command, self.artifacts_dir, self.fixtures_dir)
        self._jobs[job_id] = job
        self._executor.submit(job.run)
        return job_id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)
