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
    """FastAPI TestClient with every provider key cleared (unit test mode).

    Clears Gemini AND multi-model (TRIAGE_*) keys so `_has_model_key()` returns
    False regardless of what .env loaded — otherwise a configured GLM provider
    would make these unit tests hit the real LLM.
    """
    for key in (
        "GOOGLE_API_KEY", "GEMINI_API_KEY",
        "TRIAGE_MODEL_PROVIDER", "TRIAGE_MODEL", "TRIAGE_API_BASE", "TRIAGE_API_KEY",
        "ZHIPUAI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
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
        assert "PRD" in resp.text


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


# ---------------------------------------------------------------------------
# HITL session endpoints (add-web-frontend)
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from main import configure_static  # noqa: E402
from models.schemas import (  # noqa: E402
    AuditEntry,
    ClarifyingQuestion,
    PmAnswer,
    PolicyDecision,
    SessionState,
    TriageReport,
    Verdict,
)
from sessions.registry import SessionRegistry  # noqa: E402


def _report(
    verdict: Verdict = Verdict.PASS,
    status: str = "completed",
    clarifying=None,
    session_id=None,
):
    return TriageReport(
        prd_id="prd-002",
        verdict=verdict,
        status=status,
        clarifying_questions=clarifying or [],
        session_id=session_id,
        audit_trail=[AuditEntry(stage="intake", status="completed")],
        policy_decision=PolicyDecision(allowed=True),
    )


class TestPrdsEndpoint:
    def test_get_prds_returns_list(self, client):
        resp = client.get("/prds")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 5
        first = data[0]
        for key in ("id", "title", "status", "updated_at"):
            assert key in first


class TestTriageSessionAware:
    def test_post_triage_awaiting_pm_returns_session_id(self, client, monkeypatch):
        report = _report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="awaiting_pm",
            session_id="sess-abc",
            clarifying=[ClarifyingQuestion(question_id="q1", question="Q?")],
        )
        monkeypatch.setattr(
            "main.start_triage", lambda prd_id: (report, "sess-abc")
        )
        resp = client.post("/triage", json={"prd_id": "prd-002"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "awaiting_pm"
        assert data["session_id"] == "sess-abc"

    def test_post_triage_completed_returns_null_session(self, client, monkeypatch):
        report = _report(verdict=Verdict.PASS, status="completed")
        monkeypatch.setattr("main.start_triage", lambda prd_id: (report, None))
        resp = client.post("/triage", json={"prd_id": "prd-001"})
        data = resp.json()
        assert data["status"] == "completed"
        assert data["session_id"] is None

    def test_post_triage_reject_terminated(self, client, monkeypatch):
        report = _report(verdict=Verdict.REJECT, status="terminated")
        monkeypatch.setattr("main.start_triage", lambda prd_id: (report, None))
        resp = client.post("/triage", json={"prd_id": "prd-003"})
        data = resp.json()
        assert data["verdict"] == "reject"
        assert data["status"] == "terminated"
        assert data["session_id"] is None

    def test_legacy_post_triage_shape_preserved(self, client, monkeypatch):
        """Existing curl consumers still see verdict/prd_id/audit_trail."""
        report = _report(verdict=Verdict.PASS, status="completed")
        monkeypatch.setattr("main.start_triage", lambda prd_id: (report, None))
        resp = client.post("/triage", json={"prd_id": "prd-001"})
        data = resp.json()
        for key in ("verdict", "prd_id", "audit_trail"):
            assert key in data


class TestResumeEndpoint:
    def test_resume_endpoint_returns_final_report(self, client, monkeypatch):
        finalized = _report(verdict=Verdict.NEEDS_CLARIFICATION, status="completed")
        captured = {}

        def fake_resume(session_id, answers, override=False):
            captured["session_id"] = session_id
            captured["answers"] = answers
            captured["override"] = override
            finalized.pm_responses = list(answers)
            return finalized

        monkeypatch.setattr("main.resume_triage", fake_resume)
        resp = client.post(
            "/triage/sessions/sess-abc/resume",
            json={"answers": [{"question_id": "q1", "answer": "p95 < 200ms"}]},
        )
        assert resp.status_code == 200
        assert captured["session_id"] == "sess-abc"
        assert captured["override"] is False
        data = resp.json()
        assert data["status"] == "completed"
        assert data["pm_responses"][0]["answer"] == "p95 < 200ms"

    def test_resume_endpoint_override(self, client, monkeypatch):
        finalized = _report(verdict=Verdict.PASS, status="completed")
        monkeypatch.setattr(
            "main.resume_triage",
            lambda sid, ans, override=False: finalized,
        )
        resp = client.post(
            "/triage/sessions/sess-abc/resume",
            json={"answers": [], "override": True},
        )
        assert resp.status_code == 200
        assert resp.json()["verdict"] == "pass"

    def test_resume_unknown_session_404(self, client, monkeypatch):
        from models.schemas import SessionNotFound

        def raise_not_found(session_id, answers, override=False):
            raise SessionNotFound(session_id)

        monkeypatch.setattr("main.resume_triage", raise_not_found)
        resp = client.post("/triage/sessions/missing/resume", json={"answers": []})
        assert resp.status_code == 404
        assert "error" in resp.json()


class TestSessionStatusEndpoint:
    def test_session_status_returns_state(self, client, monkeypatch):
        reg = SessionRegistry()
        now = datetime.now(timezone.utc)
        partial = _report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="awaiting_pm",
            clarifying=[ClarifyingQuestion(question_id="q1", question="Q?")],
        )
        state = SessionState(
            prd_id="prd-002",
            prd_content="x",
            policy_decision=PolicyDecision(allowed=True),
            partial_report=partial,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        sid = reg.create(state)
        monkeypatch.setattr("main.get_session_registry", lambda: reg)

        resp = client.get(f"/triage/sessions/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "awaiting_pm"
        assert data["prd_id"] == "prd-002"
        assert "expires_at" in data

    def test_status_unknown_session_404(self, client, monkeypatch):
        monkeypatch.setattr("main.get_session_registry", lambda: SessionRegistry())
        resp = client.get("/triage/sessions/nonexistent")
        assert resp.status_code == 404
        assert "error" in resp.json() or "detail" in resp.json()


class TestRenderReport:
    def test_render_report_returns_markdown(self, client):
        report = {
            "prd_id": "prd-001",
            "verdict": "pass",
            "status": "completed",
        }
        resp = client.post("/render-report", json=report)
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        assert "## 審計軌跡" in resp.text  # Chinese section from format_report
        assert "prd-001" in resp.text
        assert "attachment" in resp.headers["content-disposition"]
        assert "prd-001-triage-report.md" in resp.headers["content-disposition"]


class TestStaticMount:
    def test_static_files_mounted_when_dist_exists(self, tmp_path):
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<html>SPA root</html>")
        app2 = FastAPI()

        @app2.get("/health")
        def h():
            return {"status": "ok"}

        assert configure_static(app2, dist) is True
        c = TestClient(app2)
        root = c.get("/")
        assert root.status_code == 200
        assert "SPA root" in root.text
        # API route takes precedence over the static mount.
        health = c.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

    def test_configure_static_returns_false_when_missing(self, tmp_path):
        app2 = FastAPI()
        assert configure_static(app2, tmp_path / "does-not-exist") is False

    def test_server_starts_without_dist(self, client):
        """Server serves health + a root HTML page regardless of dist presence."""
        assert client.get("/health").status_code == 200
        root = client.get("/")
        assert root.status_code == 200
        assert "PRD" in root.text
