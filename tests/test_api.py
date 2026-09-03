"""Backend API tests against the committed demo snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.app import create_app
from groundtruth.api.settings import ApiSettings
from groundtruth.config import PROJECT_ROOT


@pytest.fixture
def client():
    settings = ApiSettings()
    settings.artifacts_dir = PROJECT_ROOT / "demo" / "artifacts"
    settings.static_dir = PROJECT_ROOT / "src" / "groundtruth" / "api" / "static"
    app = create_app(settings)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_policy(client: TestClient) -> None:
    r = client.get("/api/policy")
    assert r.status_code == 200
    assert "policy_hash" in r.json()


def test_demo(client: TestClient) -> None:
    r = client.get("/api/demo")
    assert r.status_code == 200
    assert r.json()["project_key"] == "AUTO"


def test_runs(client: TestClient) -> None:
    r = client.get("/api/runs")
    assert r.status_code == 200
    labels = {run["label"] for run in r.json()}
    assert labels >= {"audit", "score", "report", "plan", "deliver"}


def test_run_detail(client: TestClient) -> None:
    runs = client.get("/api/runs").json()
    audit_run = next(r for r in runs if r["label"] == "audit")
    r = client.get(f"/api/runs/{audit_run['run_dir']}")
    assert r.status_code == 200
    assert "discrepancies.json" in r.json()["files"]


def test_run_file_path_traversal(client: TestClient) -> None:
    runs = client.get("/api/runs").json()
    audit_run = next(r for r in runs if r["label"] == "audit")
    r = client.get(f"/api/runs/{audit_run['run_dir']}/files/../ledger.jsonl")
    assert r.status_code == 404


def test_score_latest(client: TestClient) -> None:
    r = client.get("/api/score/latest")
    assert r.status_code == 200
    data = r.json()
    assert 0.0 <= data["total"] <= 1.0
    assert len(data["dimensions"]) == 5


def test_score_history(client: TestClient) -> None:
    r = client.get("/api/score/history")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_discrepancies(client: TestClient) -> None:
    r = client.get("/api/discrepancies")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_discrepancies_filter(client: TestClient) -> None:
    r = client.get("/api/discrepancies?severity=medium")
    assert r.status_code == 200
    assert all(d["severity"] == "medium" for d in r.json())


def test_plan(client: TestClient) -> None:
    r = client.get("/api/plan/latest")
    assert r.status_code == 200
    assert r.json()["velocity"] > 0


def test_report(client: TestClient) -> None:
    r = client.get("/api/report/latest")
    assert r.status_code == 200
    assert "prose" in r.json()


def test_report_markdown(client: TestClient) -> None:
    r = client.get("/api/report/markdown")
    assert r.status_code == 200
    assert "Standup" in r.text


def test_delivery(client: TestClient) -> None:
    r = client.get("/api/delivery/latest")
    assert r.status_code == 200
    assert r.json()["ticket_key"] == "AUTO-2"


def test_trace(client: TestClient) -> None:
    r = client.get("/api/trace/latest")
    assert r.status_code == 200
    assert len(r.json()["bindings"]) == 1


def test_ledger(client: TestClient) -> None:
    r = client.get("/api/ledger")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_ledger_integrity(client: TestClient) -> None:
    r = client.get("/api/ledger/integrity")
    assert r.status_code == 200
    assert all(v["valid"] for v in r.json())


def test_agents(client: TestClient) -> None:
    r = client.get("/api/agents/summary")
    assert r.status_code == 200
    assert r.json()["total_actions"] > 0


def test_jobs_invalid_command(client: TestClient) -> None:
    r = client.post("/api/jobs", json={"command": "seed"})
    assert r.status_code == 400
