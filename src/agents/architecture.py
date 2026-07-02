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

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from doc_mcp.repository import get_architecture_context
from models.schemas import ArchitectureReport

ARCHITECTURE_INSTRUCTION = """\
You are an **Architecture Fit Assessor** for Product Requirement Documents.

## Your job
Evaluate whether the PRD fits within the existing system architecture or \
introduces conflicts, new components, or integration risks.

## Step 1: Read the architecture context
Call the `get_architecture_context` tool to retrieve:
- The current system architecture document (services, data models, API surface)
- The 3 most recent Architecture Decision Records (ADRs)

## Step 2: Evaluate the PRD against the architecture

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
- Always call `get_architecture_context` FIRST before evaluating. Do not \
  evaluate based on assumptions about the system.
- If the tool returns empty architecture_doc, note it in raw_analysis and \
  evaluate based on general best practices.
"""

# Wrap the repository function as an ADK FunctionTool so the LLM agent can
# call it during reasoning. The tool signature (no args → dict) is
# auto-derived from the function's type hints.
get_arch_context_tool = FunctionTool(func=get_architecture_context)

architecture_checker = LlmAgent(
    name="architecture_checker",
    description=(
        "Reads the ShopFlow architecture doc + ADRs via the Document MCP "
        "repository and evaluates the PRD for conflicts, new-service "
        "requirements, and integration points."
    ),
    model="gemini-2.5-flash",
    instruction=ARCHITECTURE_INSTRUCTION,
    output_schema=ArchitectureReport,
    output_key="architecture_report",
    tools=[get_arch_context_tool],
)
