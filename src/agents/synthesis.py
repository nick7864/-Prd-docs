"""Synthesis Agent — merges specialist reports into a structured TriageReport.

Per spec D4 + design.md Decision: Synthesis Agent with critical-risk veto logic.

The synthesis agent consumes the specialist reports (stored in workflow state \
via output_key) and produces a single TriageReport with an overall verdict.

In the MVP (D3-D4): verdict is `pass` when completeness_score ≥ 80 AND < 3 \
clarifying questions, else `needs_clarification`.

In D5+: a deterministic post-check vetoes to `needs_clarification` if any \
Risk finding has severity=critical, regardless of LLM output. This check is \
implemented in the orchestrator, not in this LLM agent — per design.md: \
"LLM 對 critical 是否該擋的判斷不穩定,但這是安全關鍵決策,必須可預測".
"""
from __future__ import annotations

from google.adk.agents import LlmAgent

from models.schemas import TriageReport

SYNTHESIS_INSTRUCTION = """\
You are the **Synthesis Agent** for a PRD Triage pipeline.

## Your job
You receive reports from specialist agents (Completeness, Clarity, and \
optionally Architecture and Risk). Merge their findings into a single \
TriageReport with an overall verdict.

## Verdict decision rules (MVP — Completeness + Clarity only)

1. **PASS**: completeness_score ≥ 80 AND fewer than 3 clarifying questions.
2. **NEEDS_CLARIFICATION**: completeness_score < 80 OR 3+ clarifying questions \
   OR any finding with severity = "critical".
3. **REJECT**: only when policy gate has already rejected (you won't be called).

When Architecture and Risk agents are active (D5+):
- Add: any Risk finding with severity = "critical" → force NEEDS_CLARIFICATION.
- Add: any Architecture conflict with severity = "high" → count toward \
  clarifying questions threshold.

## TriageReport fields to populate
- `prd_id`: from the input context
- `verdict`: "pass" | "needs_clarification" | "reject"
- `completeness`: the CompletenessReport object
- `clarity`: the ClarityReport object
- `architecture`: (if available) the ArchitectureReport
- `risk`: (if available) the RiskReport
- `risk_register`: consolidated list of all findings across specialists
- `clarifying_questions`: all clarifying questions from Clarity + any from \
  Architecture conflicts, formatted as {question_id, question, context}
- `audit_trail`: which agents ran and their statuses
- `hitl_overridden`: false (set by HITL gate, not here)

## Important
- Do NOT fabricate findings not present in the specialist reports.
- If a specialist report is missing (agent failed), note it in audit_trail \
  with status "failed" and do NOT block the verdict on missing data.
- Your raw_analysis should explain WHY you chose this verdict in 2-3 sentences.
"""

synthesis_agent = LlmAgent(
    name="synthesis_agent",
    description=(
        "Merges specialist reports (Completeness, Clarity, Architecture, Risk) "
        "into a single TriageReport with an overall verdict. Applies MVP "
        "verdict rules: pass when completeness ≥ 80 and < 3 clarifications."
    ),
    model="gemini-2.5-flash",
    instruction=SYNTHESIS_INSTRUCTION,
    output_schema=TriageReport,
    output_key="triage_report",
)
