"""Tests for the FastAPI server (src/main.py).

Verifies the deployment artifact works without GOOGLE_API_KEY for:
- GET /health — health check
- POST /triage with prd-003 — policy gate rejection (no LLM needed)
- POST /triage with unknown prd_id — intake failure
- POST /triage with clean PRD without API key — graceful termination
- GET / — landing page
"""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    """FastAPI TestClient with GOOGLE_API_KEY removed (unit test mode)."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from main import app
    return TestClient(app)


@pytest.fixture
def client_with_key(monkeypatch):
    """FastAPI TestClient simulating GOOGLE_API_KEY presence (for route shape only)."""
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key-for-route-test")
    from main import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "service" in body


class TestRootEndpoint:
    def test_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "PRD Triage" in resp.text


class TestTriageEndpoint:
    def test_policy_reject_prd_003(self, client):
        """prd-003 contains an API key — policy gate rejects without LLM."""
        resp = client.post("/triage", json={"prd_id": "prd-003"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "reject"
        assert data["status"] == "terminated"
        assert data["policy_decision"]["allowed"] is False
        violation_types = {v["type"] for v in data["policy_decision"]["violations"]}
        assert "google_api_key" in violation_types

    def test_unknown_prd_returns_reject(self, client):
        """Unknown PRD id — intake fails, verdict=reject."""
        resp = client.post("/triage", json={"prd_id": "nonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "reject"
        assert data["status"] == "terminated"

    def test_clean_prd_without_api_key_terminates(self, client):
        """prd-001 is clean but without API key, specialists can't run."""
        resp = client.post("/triage", json={"prd_id": "prd-001"})
        assert resp.status_code == 200
        data = resp.json()
        # Without API key, pipeline terminates after policy gate
        assert data["status"] == "terminated"
        # Policy gate passed (no violations)
        if data.get("policy_decision"):
            assert data["policy_decision"]["allowed"] is True

    def test_all_five_prds_respond(self, client):
        """All 5 sample PRDs should produce a valid JSON response."""
        for prd_id in ["prd-001", "prd-002", "prd-003", "prd-004", "prd-005"]:
            resp = client.post("/triage", json={"prd_id": prd_id})
            assert resp.status_code == 200, f"{prd_id} returned {resp.status_code}"
            data = resp.json()
            assert "verdict" in data
            assert "prd_id" in data
            assert data["prd_id"] == prd_id

    def test_triage_response_has_audit_trail(self, client):
        """Every triage response includes an audit_trail."""
        resp = client.post("/triage", json={"prd_id": "prd-003"})
        data = resp.json()
        assert "audit_trail" in data
        assert len(data["audit_trail"]) >= 2  # at least intake + policy
        stages = {e["stage"] for e in data["audit_trail"]}
        assert "intake" in stages

    def test_missing_prd_id_returns_422(self, client):
        """POST without prd_id in body returns validation error."""
        resp = client.post("/triage", json={})
        assert resp.status_code == 422
