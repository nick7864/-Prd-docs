"""ADK specialist agents for PRD triage.

Root agent: ``root_agent`` (SequentialAgent pipeline with ParallelAgent fan-out).

Run locally:
    uv run adk web           # playground UI at localhost:8000
    uv run adk run agents    # CLI mode

Programmatic:
    from agents.orchestrator import triage
    report = triage("prd-001")
"""
from .orchestrator import root_agent, triage

__all__ = ["root_agent", "triage"]
