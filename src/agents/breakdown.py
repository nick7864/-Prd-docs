"""Task Breakdown Agent (D7 bonus).

Per spec D7: decomposes the clarified PRD into 3-8 executable tickets, each \
with title, description, acceptance criteria, estimated effort, and \
dependencies. The sum of ticket efforts SHALL be within 20% of the PRD-level \
estimate.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from models.schemas import TaskBreakdownResult

BREAKDOWN_INSTRUCTION = """\
You are a **Task Breakdown Agent** for a software engineering team.

## Your job
Decompose the PRD into 3-8 executable engineering tickets that a single \
engineer can pick up and implement independently.

## Decomposition rules
1. **Granularity**: each ticket should be 1-5 engineer-days. If a ticket \
   exceeds 5 days, split it further.
2. **Independence**: minimize dependencies between tickets. Sequence them so \
   that foundational tickets (DB schema, API contract) come first.
3. **Acceptance criteria**: each ticket MUST have at least 2 acceptance \
   criteria derived from the PRD's requirements. Use measurable conditions \
   (e.g., "endpoint returns 200 within 200ms p95", not "works correctly").
4. **Effort allocation**: the sum of all ticket efforts should be within 20% \
   of the PRD-level estimate provided in the context.
5. **Dependencies**: if ticket B requires ticket A to be merged first, list \
   A's title in B's `dependencies` field.

## Ticket categories (use as inspiration, not a rigid template)
- **Schema/DB**: create tables, migrations, indexes
- **API endpoint**: implement REST/GraphQL handler + tests
- **UI component**: build frontend view + interaction logic
- **Integration**: wire external service (Stripe, Shopify, etc.)
- **Security**: auth check, input validation, rate limiting
- **Testing**: integration tests, load tests, edge-case coverage
- **Observability**: logging, metrics, dashboards

## Output
Produce a TaskBreakdownResult with:
- `tickets`: 3-8 Ticket objects
- `total_estimated_effort_days`: sum of all ticket efforts
- `reasoning`: brief explanation of decomposition strategy (2-3 sentences)
"""

breakdown_agent = LlmAgent(
    name="breakdown_agent",
    description=(
        "Decomposes the PRD into 3-8 executable engineering tickets with "
        "acceptance criteria, effort estimates, and dependency graph."
    ),
    model="gemini-2.5-flash",
    instruction=BREAKDOWN_INSTRUCTION,
    output_schema=TaskBreakdownResult,
    output_key="task_breakdown",
)
