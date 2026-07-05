"""Synthesis Agent — advisory merger of specialist reports.

Per change ``fix-synthesis-state``: synthesis is an ADVISORY LlmAgent. It emits
a small ``SynthesisOutput`` (verdict suggestion + reasoning + clarifying
questions); the orchestrator deterministically assembles the final
``TriageReport`` from specialist state and computes the authoritative verdict.
``output_key`` is ``"synthesis_output"``; the orchestrator reads it
tolerantly and degrades gracefully when it is absent.
"""
from __future__ import annotations

import json

from google.adk.agents import LlmAgent

from models.schemas import SynthesisOutput

from ._model import build_model

SYNTHESIS_INSTRUCTION = """\
You are the **Synthesis Agent** for a PRD Triage pipeline — an ADVISORY role.
You receive reports from the specialist agents (JSON) and propose an overall
verdict. The system applies its own deterministic rule on top of your
suggestion, so focus on sound reasoning, not on being the final decider.

## Specialist reports

### Completeness
{completeness_report}

### Clarity
{clarity_report}

### Architecture (optional — "MISSING" means the agent did not run)
{architecture_report?}

### Risk (optional — "MISSING" means the agent did not run)
{risk_report?}

## Verdict suggestion rules
1. **PASS**: completeness_score >= 80 AND fewer than 3 clarifying questions.
2. **NEEDS_CLARIFICATION**: otherwise, or any finding with severity = "critical".
3. **REJECT**: never (the policy gate already handled rejection upstream).

## Output
Produce a SynthesisOutput with:
- `verdict`: your suggested "pass" | "needs_clarification".
- `raw_analysis`: 2-3 sentences explaining WHY.
- `clarifying_questions`: list of {question_id, question, context?} drawn from
  clarity ambiguities and architecture conflicts you consider worth asking.

Do NOT include prd_id, audit_trail, or the specialist sub-objects — the
orchestrator fills those. Do NOT fabricate findings not in the reports above.

## Output language
All human-readable text fields (`raw_analysis`, and the `question`/`context` of \
each clarifying question) MUST be written in Traditional Chinese (繁體中文). \
Field names and `verdict` enum values stay in English as defined by the schema.
"""


def _prepare_synthesis_inputs(callback_context):
    """JSON-serialize specialist state before synthesis runs.

    ADK's ``{var}`` injection uses ``str(value)``, so a dict would render as
    Python repr (single quotes) rather than JSON. We overwrite each specialist
    state key with a JSON string so the instruction receives clean JSON. An
    absent optional specialist becomes the literal ``"MISSING"`` so the prompt
    can tell "agent did not run" apart from "agent produced an empty report".
    """
    state = callback_context.state
    for key in ("completeness_report", "clarity_report",
                "architecture_report", "risk_report"):
        raw = state.get(key)
        if isinstance(raw, dict):
            state[key] = json.dumps(raw, ensure_ascii=False, default=str)
    for key in ("architecture_report", "risk_report"):
        if state.get(key) is None:
            state[key] = "MISSING"
    return None


synthesis_agent = LlmAgent(
    name="synthesis_agent",
    description=(
        "Advisory merger of specialist reports into a small SynthesisOutput "
        "(verdict suggestion + reasoning + clarifying questions). The "
        "orchestrator assembles the final TriageReport deterministically."
    ),
    model=build_model(),
    instruction=SYNTHESIS_INSTRUCTION,
    output_schema=SynthesisOutput,
    output_key="synthesis_output",
    before_agent_callback=_prepare_synthesis_inputs,
)
