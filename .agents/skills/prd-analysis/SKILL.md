---
name: prd-analysis
description: >
  Trigger the PRD Triage pipeline to analyze a Product Requirement Document
  for completeness, clarity, architecture fit, and risk. Produces a structured
  TriageReport with verdict, findings, and clarifying questions.
license: MIT
compatibility: Requires the PRD Triage Agent service running locally or deployed.
---

# PRD Analysis Skill

## When to trigger

- User asks to "triage", "analyze", or "review" a PRD
- User mentions a PRD identifier (e.g., "prd-001", "the dark mode PRD")
- User wants to check if a PRD is "ready for engineering"

## What this skill does

Calls the PRD Triage Agent pipeline, which:

1. **Reads** the PRD from the document repository (via MCP server).
2. **Policy gate** — rejects PRDs containing API keys, emails, or other PII.
3. **Parallel specialist analysis**:
   - Completeness Checker — are all 5 required sections present?
   - Clarity Checker — any vague terms, contradictions, or undefined jargon?
   - (D5+) Architecture Fit — conflicts with existing system?
   - (D5+) Risk & Compliance — security, GDPR, PCI-DSS risks?
4. **Synthesis** — merges findings into a single TriageReport with a verdict.
5. (D5+) **HITL gate** — if verdict is `needs_clarification`, pauses and asks the PM.
6. (D7) **Estimation + Task Breakdown** — effort estimate and ticket decomposition.

## How to interpret the TriageReport

| Verdict | Meaning | Next step |
|---|---|---|
| `pass` | PRD is ready for engineering | Proceed to estimation |
| `needs_clarification` | PRD has gaps the PM must resolve | Present `clarifying_questions` to PM |
| `reject` | PRD contains PII/secrets or is unreadable | Fix policy violation, re-submit |

## Procedure

1. Identify the `prd_id` from the user's request (e.g., "prd-001").
2. Call the triage endpoint:
   ```
   POST /triage
   {"prd_id": "prd-001"}
   ```
3. Parse the `TriageReport` JSON response.
4. Present results to the user:
   - **Verdict** (pass / needs_clarification / reject)
   - **Completeness score** and missing sections
   - **Clarity findings** with generated questions
   - **Risk register** (if D5 agents are active)
5. If verdict is `needs_clarification`, ask the user (acting as PM) to answer the clarifying questions.
6. If verdict is `reject`, explain which policy rule was violated and where.

## Example session

> **User**: "Triage prd-002"
>
> **Skill output**:
> - Verdict: `needs_clarification`
> - Completeness score: 45/100
> - Missing sections: `acceptance_criteria` (severity: high)
> - Clarity: 2 vague terms ("fast", "scalable")
> - Clarifying questions:
>   1. "Define target p95 latency in ms for search results"
>   2. "Specify expected peak QPS for the search service"
> - Recommendation: Add Given/When/Then acceptance criteria and quantify NFR targets before re-submitting.
