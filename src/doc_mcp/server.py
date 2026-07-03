"""Document MCP server — exposes the PRD repository as MCP tools.

Module name is ``doc_mcp`` (not ``mcp``) to avoid shadowing the upstream
``mcp`` PyPI package during ``from mcp.server.fastmcp import FastMCP`` imports.
See design.md → Decision: Rename src/mcp to src/doc_mcp.

Run as a stdio MCP server:
    uv run python -m doc_mcp.server

Or register via the ADK MCPToolset from a consumer agent (see
``src/agents/orchestrator.py`` in D4).

The four tools mirror ``doc_mcp.repository`` 1:1 — protocol concerns
(FastMCP registration, schema generation, stdio transport) live here, pure
file/embedding logic lives in repository.py for unit testability.
"""
from __future__ import annotations

from dotenv import load_dotenv

# Load .env (e.g. GOOGLE_API_KEY) before sibling modules read env vars.
# No-op when .env is absent; see .env.example for required vars.
load_dotenv()

from mcp.server.fastmcp import FastMCP

from .repository import (
    get_architecture_context as _get_architecture_context,
    get_prd as _get_prd,
    get_similar_prds as _get_similar_prds,
    list_prds as _list_prds,
)

mcp = FastMCP(
    name="document-repository",
    instructions=(
        "PRD and architecture document repository for the PRD Triage Agent. "
        "Exposes four read-only document tools (list_prds, get_prd, "
        "get_architecture_context, get_similar_prds) plus triage_prd which "
        "runs the full multi-agent triage pipeline."
    ),
)


@mcp.tool()
def list_prds() -> list[dict]:
    """List all PRDs in the repository with metadata.

    Returns a list of objects: ``{id, title, status, updated_at}``.
    Empty repository returns ``[]`` (not an error).
    """
    return _list_prds()


@mcp.tool()
def get_prd(prd_id: str) -> dict:
    """Return full PRD content by identifier.

    Returns ``{id, title, content, metadata}`` on success.
    Returns ``{error: "PRD not found: <id>"}`` if the id is unknown — never raises.
    """
    return _get_prd(prd_id)


@mcp.tool()
def get_architecture_context() -> dict:
    """Return the ShopFlow architecture document and the 3 most recent ADRs.

    Returns ``{architecture_doc: str, adrs: [{id, title, status, content}]}``.
    """
    return _get_architecture_context()


@mcp.tool()
def get_similar_prds(query: str, top_k: int = 3) -> list[dict]:
    """Semantic search for similar historical PRDs.

    Uses Gemini embeddings when ``GOOGLE_API_KEY``/``GEMINI_API_KEY`` is set;
    falls back to keyword-overlap scoring otherwise so the pipeline still works
    in offline / no-key states. Returns up to ``top_k`` results sorted by
    descending ``similarity_score``.
    """
    return _get_similar_prds(query, top_k)


@mcp.tool()
def triage_prd(prd_id: str) -> dict:
    """Run the full PRD triage pipeline on the given PRD.

    Executes: intake → policy gate → 4 specialist agents in parallel
    (completeness, clarity, architecture, risk) → synthesis. Returns the
    complete TriageReport as a dict, including verdict
    (pass / needs_clarification / reject), specialist reports, clarifying
    questions, and audit trail.

    Note: this is a long-running tool (10-30s) because it calls multiple LLM
    agents. Requires ``GOOGLE_API_KEY`` for the LLM-based analysis; without it,
    returns an intake/policy-only result with ``status="terminated"``. Never
    raises — expected failures (missing PRD, policy reject) come back as a
    TriageReport with the appropriate verdict.
    """
    from agents.orchestrator import triage

    report = triage(prd_id)
    return report.model_dump(mode="json")


def main() -> None:
    """Entry point for ``python -m doc_mcp.server``."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
