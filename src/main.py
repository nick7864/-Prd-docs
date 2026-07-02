"""FastAPI server for the PRD Triage Agent.

Deployed to Google Cloud Run (D6). Exposes:
    POST /triage        — run the full pipeline on a PRD
    GET  /health        — health check
    GET  /              — landing page

Run locally:
    uv run uvicorn src.main:app --reload --port 8080
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from agents.orchestrator import triage

app = FastAPI(
    title="PRD Triage Agent",
    description="Multi-agent PRD intake checkup for software teams.",
    version="0.1.0",
)


class TriageRequest(BaseModel):
    prd_id: str


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """
    <html><body style="font-family: sans-serif; max-width: 600px; margin: 40px auto;">
    <h1>PRD Triage Agent</h1>
    <p>Multi-agent PRD intake checkup for software teams.</p>
    <h3>Usage</h3>
    <pre>curl -X POST {host}/triage -H 'Content-Type: application/json' -d '{"prd_id": "prd-001"}'</pre>
    </body></html>
    """


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "prd-triage-agent"}


@app.post("/triage")
def run_triage(req: TriageRequest) -> JSONResponse:
    report = triage(req.prd_id)
    return JSONResponse(content=report.model_dump(mode="json"))
