"""API settings, read from environment."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from groundtruth.config import PROJECT_ROOT


def _bundle_dir() -> Path | None:
    """Return the PyInstaller one-file extraction directory, if active."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).resolve()  # type: ignore[attr-defined]
    return None


class ApiSettings:
    """Read-only settings container. Defaults point at the committed demo snapshot."""

    def __init__(self) -> None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)

        bundle = _bundle_dir()
        self.artifacts_dir = Path(
            os.getenv(
                "GT_API_ARTIFACTS_DIR",
                bundle / "demo" / "artifacts" if bundle else PROJECT_ROOT / "demo" / "artifacts",
            )
        ).resolve()
        self.fixtures_dir = Path(
            os.getenv(
                "GT_API_FIXTURES_DIR",
                bundle / "demo" / "fixtures" if bundle else PROJECT_ROOT / "demo" / "fixtures",
            )
        ).resolve()
        self.static_dir = Path(
            os.getenv(
                "GT_API_STATIC_DIR",
                bundle / "static" if bundle else PROJECT_ROOT / "src" / "groundtruth" / "api" / "static",
            )
        ).resolve()
        self.api_host = os.getenv("GT_API_HOST", "0.0.0.0")
        self.api_port = int(os.getenv("PORT", os.getenv("GT_API_PORT", "8000")))
        self.demo_mode = os.getenv("GT_API_DEMO_MODE", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.connections_path = Path(
            os.getenv("GT_CONNECTIONS_PATH", PROJECT_ROOT / ".groundtruth" / "connections.json")
        ).resolve()
        self.allowed_origins = [
            origin.strip()
            for origin in os.getenv("GT_ALLOWED_ORIGINS", "*").split(",")
            if origin.strip()
        ]
        self.oauth_redirect_base = os.getenv(
            "GT_OAUTH_REDIRECT_BASE", "http://localhost:8000"
        ).rstrip("/")
        self.github_client_id = os.getenv("GT_GITHUB_CLIENT_ID", "")
        self.github_client_secret = os.getenv("GT_GITHUB_CLIENT_SECRET", "")
        self.jira_client_id = os.getenv("GT_JIRA_CLIENT_ID", "")
        self.jira_client_secret = os.getenv("GT_JIRA_CLIENT_SECRET", "")
        self.github_oauth_available = bool(self.github_client_id and self.github_client_secret)
        self.jira_oauth_available = bool(self.jira_client_id and self.jira_client_secret)
