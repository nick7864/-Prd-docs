"""FastAPI server for the PRD Triage Agent.

Exposes the session-aware triage pipeline over HTTP:
    GET  /health                       — health check
    GET  /prds                         — list PRDs in the repository
    POST /triage                       — run triage (pauses for HITL when needed)
    POST /triage/sessions/{id}/resume  — submit PM answers / override
    GET  /triage/sessions/{id}         — poll a paused session's status
    GET  /                              — SPA (when frontend/dist built) or landing

Run locally:
    uv run uvicorn src.main:app --reload --port 8080
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.orchestrator import get_session_registry, resume_triage, start_triage
from doc_mcp.repository import list_prds
from models.schemas import ResumeTriageRequest, SessionNotFound, TriageReport
from report import format_report

log = logging.getLogger("prd-triage-agent")

app = FastAPI(
    title="PRD Triage Agent",
    description="Multi-agent PRD intake checkup for software teams.",
    version="0.1.0",
)


class TriageRequest(BaseModel):
    prd_id: str


@app.exception_handler(SessionNotFound)
def _session_not_found_handler(_request, _exc: SessionNotFound):
    return JSONResponse(
        status_code=404,
        content={"error": "工作階段已過期或不存在"},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "prd-triage-agent"}


@app.get("/prds")
def list_all_prds() -> list[dict]:
    return list_prds()


@app.post("/triage")
def run_triage(req: TriageRequest) -> JSONResponse:
    report, _session_id = start_triage(req.prd_id)
    return JSONResponse(content=report.model_dump(mode="json"))


@app.post("/triage/sessions/{session_id}/resume")
def resume_session(session_id: str, req: ResumeTriageRequest) -> JSONResponse:
    report = resume_triage(session_id, req.answers, override=req.override)
    return JSONResponse(content=report.model_dump(mode="json"))


@app.get("/triage/sessions/{session_id}")
def session_status(session_id: str) -> JSONResponse:
    state = get_session_registry().get(session_id)
    if state is None:
        raise HTTPException(
            status_code=404, detail="工作階段已過期或不存在"
        )
    return JSONResponse(
        content={
            "status": state.partial_report.status,
            "prd_id": state.prd_id,
            "expires_at": state.expires_at.isoformat(),
        }
    )


@app.post("/render-report")
def render_report_md(report: TriageReport) -> Response:
    """Render a TriageReport (posted from the frontend) as downloadable Markdown.

    Keeps `format_report()` as the single source of truth for the 8-section
    Chinese Markdown layout; the frontend just triggers a download.
    """
    markdown = format_report(report)
    filename = f"{report.prd_id}-triage-report.md"
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_LANDING_HTML = """
<html><body style="font-family: sans-serif; max-width: 600px; margin: 40px auto;">
<h1>PRD Triage Agent</h1>
<p>Multi-agent PRD intake checkup for software teams.</p>
<h3>Usage</h3>
<pre>curl -X POST {host}/triage -H 'Content-Type: application/json' -d '{"prd_id": "prd-001"}'</pre>
</body></html>
"""

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def configure_static(app: FastAPI, dist_dir: Path) -> bool:
    """Mount the built frontend at ``/`` when ``dist_dir`` exists.

    Mounted AFTER all API routes so ``/triage``, ``/health``, ``/prds`` and
    ``/triage/sessions/*`` take precedence over static assets. Returns True when
    mounted, False when the dir is missing (caller falls back to a landing page).
    """
    if not dist_dir.is_dir():
        return False
    app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
    return True


if configure_static(app, _FRONTEND_DIST):
    log.info("frontend static bundle mounted at / from %s", _FRONTEND_DIST)
else:

    @app.get("/", response_class=HTMLResponse)
    def root() -> str:
        return _LANDING_HTML
