from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, field_validator


def _project_root() -> Path:
    """Return the project root. When running as a PyInstaller bundle this is
    the directory containing the executable so .env/workspace/connections live
    next to the app the user runs.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _project_root()


class RunMode(str, Enum):
    LIVE = "live"
    RECORD = "record"
    REPLAY = "replay"


class ExecMode(str, Enum):
    DRY_RUN = "dry-run"
    PROPOSE = "propose"
    APPLY = "apply"


class Settings(BaseModel):
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    jira_auth_mode: str = "basic"  # "basic" | "oauth"
    jira_cloud_id: str = ""
    jira_access_token: str = ""
    github_token: str = ""
    github_repo_owner: str = ""
    github_repo_name: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str = ""
    run_mode: RunMode = RunMode.REPLAY
    exec_mode: ExecMode = ExecMode.DRY_RUN
    workspace_dir: Path = PROJECT_ROOT / "workspace"
    artifacts_dir: Path = PROJECT_ROOT / "artifacts"
    fixtures_dir: Path = PROJECT_ROOT / "fixtures"

    @field_validator("workspace_dir", "artifacts_dir", "fixtures_dir", mode="before")
    @classmethod
    def _resolve_path(cls, v: object) -> Path:
        return Path(v).resolve() if v else v  # type: ignore[return-value]

    @classmethod
    def from_env(cls) -> Self:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env", override=False)

        settings = cls(
            jira_base_url=os.getenv("JIRA_BASE_URL", ""),
            jira_email=os.getenv("JIRA_EMAIL", ""),
            jira_api_token=os.getenv("JIRA_API_TOKEN", ""),
            jira_project_key=os.getenv("JIRA_PROJECT_KEY", ""),
            github_token=os.getenv("GITHUB_TOKEN", ""),
            github_repo_owner=os.getenv("GITHUB_REPO_OWNER", ""),
            github_repo_name=os.getenv("GITHUB_REPO_NAME", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            workspace_dir=os.getenv("GT_WORKSPACE_DIR", PROJECT_ROOT / "workspace"),
            artifacts_dir=os.getenv("GT_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts"),
            fixtures_dir=os.getenv("GT_FIXTURES_DIR", PROJECT_ROOT / "fixtures"),
        )

        from groundtruth.connections import apply_connections

        return apply_connections(settings)

    def validate_live_mode(self) -> None:
        missing: list[str] = []
        if not self.jira_base_url:
            missing.append("JIRA_BASE_URL")
        if self.jira_auth_mode == "oauth":
            if not self.jira_access_token:
                missing.append("JIRA_ACCESS_TOKEN")
            if not self.jira_cloud_id:
                missing.append("JIRA_CLOUD_ID")
        else:
            if not self.jira_email:
                missing.append("JIRA_EMAIL")
            if not self.jira_api_token:
                missing.append("JIRA_API_TOKEN")
        if not self.github_token:
            missing.append("GITHUB_TOKEN")
        if not self.llm_api_key:
            missing.append("LLM_API_KEY")
        if not self.llm_model:
            missing.append("LLM_MODEL")
        if not self.llm_base_url:
            missing.append("LLM_BASE_URL")
        if missing:
            raise RuntimeError(
                f"Live mode requires: {', '.join(missing)}. "
                "Set them in .env or connect accounts in Settings."
            )
