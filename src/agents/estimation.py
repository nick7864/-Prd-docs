"""Estimation Agent (D7 bonus).

Per spec D7: calls `get_similar_prds` for historical analogues, compares the \
target PRD scope against them, outputs a point estimate (engineer-days) with \
a confidence interval and estimation drivers. When no analogues are returned, \
sets `low_confidence: true` and produces a wider interval.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from doc_mcp.repository import get_similar_prds
from models.schemas import Estimate

ESTIMATION_INSTRUCTION = """\
You are an **Estimation Agent** for a software engineering team.

## Your job
Produce a workload estimate (in engineer-days) for implementing the PRD, \
based on historical analogues retrieved from the document repository.

## Step 1: Retrieve historical analogues
Call the `get_similar_prds` tool with a query derived from the PRD's core \
feature description. This returns the top 3 most similar historical PRDs \
with similarity scores.

## Step 2: Compare scope
For each analogue, compare:
- Feature complexity (number of new endpoints, UI screens, integrations)
- Technical uncertainty (new tech stack? new external dependency?)
- Testing burden (acceptance criteria count, edge case count)

## Step 3: Produce estimate
Output an Estimate with:
- `point_estimate_days`: your best single-number estimate
- `confidence_interval`: {low, median, high} in engineer-days
- `drivers`: 2-4 factors that raised or lowered the estimate, referencing \
  the historical analogues (e.g., "prd-005 (Inventory Sync) took 6 days for \
  a similar webhook integration pattern")
- `low_confidence`: set to `true` when:
  - No analogues returned (get_similar_prds returned [])
  - All analogues have similarity_score < 0.5
  When low_confidence is true, widen the interval (high - low > 2 × median)

## Calibration guide
| Complexity | Typical range |
|---|---|
| Simple CRUD endpoint | 1-3 days |
| New feature with UI | 5-10 days |
| Integration with external API | 3-8 days |
| Multi-service feature | 8-15 days |
| Architectural change | 10-20+ days |
"""

get_similar_prds_tool = FunctionTool(func=get_similar_prds)

estimation_agent = LlmAgent(
    name="estimation_agent",
    description=(
        "Produces effort estimate (engineer-days) with confidence interval "
        "by comparing the PRD against similar historical PRDs retrieved via "
        "the document repository."
    ),
    model="gemini-2.5-flash",
    instruction=ESTIMATION_INSTRUCTION,
    output_schema=Estimate,
    output_key="estimate",
    tools=[get_similar_prds_tool],
)
