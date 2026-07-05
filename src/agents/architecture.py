"""Architecture Fit Assessor agent (D5).

Per spec D5: an ADK LlmAgent that reads the ShopFlow architecture doc + ADRs \
(via the Document MCP server's get_architecture_context tool) and evaluates \
the PRD for conflicts with the existing system, new-service requirements, and \
integration points.

Outputs an ArchitectureReport via output_key="architecture_report".

Tool wiring: uses a FunctionTool wrapping doc_mcp.repository.\
get_architecture_context directly (in-process, no subprocess MCP needed). \
The MCP server (src/doc_mcp/server.py) still exists for external consumers \
(Claude Desktop, Antigravity) and counts toward the MCP Key Concept.
"""
from __future__ import annotations

import json

from google.adk.agents import LlmAgent

from doc_mcp.repository import get_architecture_context
from models.schemas import ArchitectureReport

from ._model import build_model


def _prepare_architecture_context(callback_context):
    """Read the architecture doc + ADRs in Python and inject as JSON.

    Replaces the previous ADK ``FunctionTool`` so the architecture agent no
    longer combines ``tools`` + ``output_schema`` (a Gemini-3.0-only pattern).
    ADK's ``{var}`` injection stringifies dicts to Python repr, so we serialize
    to JSON here for a clean prompt. A failed read writes the literal
    ``"MISSING"`` so the agent can note the absence rather than abort.
    """
    try:
        ctx = get_architecture_context()
        if isinstance(ctx, dict) and "error" in ctx:
            callback_context.state["architecture_context"] = "MISSING"
        else:
            callback_context.state["architecture_context"] = json.dumps(
                ctx, ensure_ascii=False, default=str
            )
    except Exception:
        callback_context.state["architecture_context"] = "MISSING"
    return None

ARCHITECTURE_INSTRUCTION = """\
You are an **Architecture Fit Assessor** for Product Requirement Documents.

## Your job
Evaluate whether the PRD fits within the existing system architecture or \
introduces conflicts, new components, or integration risks.

## Architecture context (pre-loaded; "MISSING" means unavailable)
{architecture_context}

## Evaluate the PRD against the architecture

### Conflicts to detect
- **Service boundary violations**: PRD asks one service to do another's job \
  (e.g., cart-svc writing to the order database directly).
- **Tech stack contradictions**: PRD mandates a tech not in the stack \
  (e.g., "use MongoDB" when ADR-002 chose PostgreSQL).
- **Auth model mismatch**: PRD proposes session-based auth when ADR-003 \
  mandates OAuth 2.0 + PKCE.
- **Data ownership violations**: PRD has service A reading/writing service B's \
  data without going through B's API.

### New-service requirements
- Does the PRD imply creating a new microservice? If so, flag it — this is a \
  significant architectural decision that needs its own ADR.
- Does the PRD require new infrastructure (new DB, new queue, new cache)? Flag it.

### Integration points
- Which existing services does this PRD touch? List them.
- Are there new API contracts? External dependencies? Third-party integrations?

## Severity for conflicts
- **high**: Directly contradicts an accepted ADR or violates service boundaries.
- **medium**: Introduces a new component or integration that needs design review.
- **low**: Minor deviation, can be resolved during implementation.

## Output
Produce an ArchitectureReport with:
- `conflicts`: list of {description, severity}
- `integration_points`: list of {description, service}
- `raw_analysis`: summary of architectural fit assessment

## Important
- The architecture context above is pre-loaded for you; do not call any tool.
  If it is "MISSING", note that in raw_analysis and evaluate based on general
  best practices.

## Output language
All human-readable text fields (`description` for conflicts/integration points, \
`raw_analysis`) MUST be written in Traditional Chinese (繁體中文). Field names \
and `severity` enum values stay in English as defined by the schema.
"""

architecture_checker = LlmAgent(
    name="architecture_checker",
    description=(
        "Reads the ShopFlow architecture doc + ADRs (pre-loaded into its prompt) "
        "and evaluates the PRD for conflicts, new-service requirements, and "
        "integration points."
    ),
    model=build_model(),
    instruction=ARCHITECTURE_INSTRUCTION,
    output_schema=ArchitectureReport,
    output_key="architecture_report",
    before_agent_callback=_prepare_architecture_context,
)
