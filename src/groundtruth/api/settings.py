"""API settings, read from environment."""

from __future__ import annotations

import os
from pathlib import Path

from groundtruth.config import PROJECT_ROOT


class ApiSettings:
    """Read-only settings container. Defaults point at the committed demo snapshot."""

    def __init__(self) -> None:
        self.artifacts_dir = Path(
            os.getenv("GT_API_ARTIFACTS_DIR", PROJECT_ROOT / "demo" / "artifacts")
        ).resolve()
        self.fixtures_dir = Path(
            os.getenv("GT_API_FIXTURES_DIR", PROJECT_ROOT / "demo" / "fixtures")
        ).resolve()
        self.static_dir = Path(
            os.getenv(
                "GT_API_STATIC_DIR",
                PROJECT_ROOT / "src" / "groundtruth" / "api" / "static",
            )
        ).resolve()
        self.api_host = os.getenv("GT_API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("GT_API_PORT", "8000"))
        self.demo_mode = os.getenv("GT_API_DEMO_MODE", "true").lower() in {
            "1",
            "true",
            "yes",
        }
