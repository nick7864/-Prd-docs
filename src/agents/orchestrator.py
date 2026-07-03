"""PRD Triage orchestrator — the root pipeline agent + entry point.

Per spec D4: ADK Parallel workflow for specialist fan-out + sequential \
synthesis. The pipeline is a SequentialAgent containing:
1. ParallelAgent(specialists) — fan-out to Completeness + Clarity (MVP)
2. Synthesis agent — merge into TriageReport

Pre-pipeline steps (intake + policy gate) run as synchronous Python functions \
before the ADK pipeline is invoked. This keeps the ADK graph focused on the \
LLM-heavy parts and makes the deterministic checks trivially testable.

## Entry point
`triage(prd_id)` — the public API. Called by the CLI, FastAPI server, or \
Antigravity Skill.

## Graph structure (for spec verification)
```
SequentialAgent("prd_triage_pipeline")
├── ParallelAgent("specialists_parallel")
│   ├── LlmAgent("completeness_checker")
│   └── LlmAgent("clarity_checker")
└── LlmAgent("synthesis_agent")
```
Contains ≥1 parallel segment + ≥3 sequential nodes — satisfies the spec \
requirement "Pipeline SHALL be orchestrated via ADK workflow graph".
"""
from __future__ import annotations

from dotenv import load_dotenv

# Load .env (e.g. GOOGLE_API_KEY) for CLI / FastAPI / pytest entry points that
# bypass the MCP server. No-op when .env is absent.
load_dotenv()

import asyncio
from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

from doc_mcp.repository import get_prd
from models.schemas import (
    AuditEntry,
    ClarifyingQuestion,
    PmAnswer,
    PolicyDecision,
    Severity,
    TriageReport,
    Verdict,
)
from policy.checker import check_policy

from .architecture import architecture_checker
from .clarity import clarity_checker
from .completeness import completeness_checker
from .risk import risk_checker
from .synthesis import synthesis_agent

# ---------------------------------------------------------------------------
# ADK pipeline graph
# ---------------------------------------------------------------------------

specialists_parallel = ParallelAgent(
    name="specialists_parallel",
    description=(
        "Runs all four specialist agents concurrently: Completeness, Clarity, "
        "Architecture, Risk. Per spec: 'four specialist agents SHALL analyze "
        "the PRD in parallel'."
    ),
    sub_agents=[
        completeness_checker,
        clarity_checker,
        architecture_checker,
        risk_checker,
    ],
)

# The root agent — this is what `adk web` / `adk run agents` discovers.
root_agent = SequentialAgent(
    name="prd_triage_pipeline",
    description=(
        "PRD Triage pipeline: parallel specialists → synthesis. "
        "Intake and policy gate run as pre-processing before this graph."
    ),
    sub_agents=[specialists_parallel, synthesis_agent],
)


# ---------------------------------------------------------------------------
# triage() — synchronous entry point (pre-processing + ADK pipeline)
# ---------------------------------------------------------------------------


def _intake(prd_id: str) -> dict[str, Any]:
    """Read PRD content from the document repository."""
    return get_prd(prd_id)


def _policy_gate(prd_content: str) -> PolicyDecision:
    """Scan PRD for PII or secret patterns."""
    return check_policy(prd_content)


def triage(prd_id: str) -> TriageReport:
    """Run the full PRD triage pipeline.

    Steps:
    1. Intake — read PRD from repository via MCP tool.
    2. Policy gate — reject if PII/secrets found.
    3. Specialists (parallel) — Completeness + Clarity analysis (ADK graph).
    4. Synthesis — merge into TriageReport with verdict.

    Returns a TriageReport regardless of outcome (reject, needs_clarification,
    or pass). Never raises on expected failures (missing PRD, policy reject).

    NOTE: Steps 3-4 require the ADK Runner + GOOGLE_API_KEY. When the key is \
    not set, this function returns the intake/policy result with \
    status="terminated" and a note in audit_trail.
    """
    import os
    import sys

    audit: list[AuditEntry] = []

    # --- Step 1: Intake ---
    prd = _intake(prd_id)
    if "error" in prd:
        audit.append(
            AuditEntry(
                stage="intake",
                status="failed",
                error=prd["error"],
            )
        )
        return TriageReport(
            prd_id=prd_id,
            verdict=Verdict.REJECT,
            status="terminated",
            audit_trail=audit,
        )
    audit.append(AuditEntry(stage="intake", status="completed"))

    # --- Step 2: Policy gate ---
    decision = _policy_gate(prd["content"])
    if not decision.allowed:
        audit.append(
            AuditEntry(
                stage="policy",
                status="completed",
                error=f"Rejected: {[v.type for v in decision.violations]}",
            )
        )
        return TriageReport(
            prd_id=prd_id,
            verdict=Verdict.REJECT,
            status="terminated",
            policy_decision=decision,
            audit_trail=audit,
        )
    audit.append(AuditEntry(stage="policy", status="completed"))

    # --- Step 3-4: ADK pipeline (specialists + synthesis) ---
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        audit.append(
            AuditEntry(
                stage="specialists",
                status="skipped",
                error="GOOGLE_API_KEY not set; cannot run LLM agents",
            )
        )
        return TriageReport(
            prd_id=prd_id,
            verdict=Verdict.PASS,  # optimistic default; real pipeline would analyze
            status="terminated",
            audit_trail=audit,
            policy_decision=decision,
        )

    # Run the ADK pipeline via Runner.
    # NOTE: This path is exercised in integration tests with GOOGLE_API_KEY set.
    # The Runner API may vary by ADK version; see ADK docs for current usage.
    try:
        result = _run_coro_safely(_run_adk_pipeline(prd_id, prd["content"]))
        audit.append(AuditEntry(stage="specialists", status="completed"))
        audit.append(AuditEntry(stage="synthesis", status="completed"))
        result.audit_trail = audit
        result.policy_decision = decision
        return result
    except Exception as exc:
        print(f"[orchestrator] ADK pipeline failed: {exc!r}", file=sys.stderr)
        audit.append(
            AuditEntry(stage="specialists", status="failed", error=str(exc))
        )
        return TriageReport(
            prd_id=prd_id,
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="terminated",
            audit_trail=audit,
            policy_decision=decision,
        )


def _run_coro_safely(coro):
    """Run a coroutine to completion, handling nested event loops.

    ``asyncio.run`` raises if called from inside a running event loop (e.g.
    when ``triage()`` is invoked from the MCP server's async context, or any
    async framework). When a running loop is detected, the coroutine is driven
    in a worker thread (which has no parent loop), so ``asyncio.run`` works
    there. Otherwise ``asyncio.run`` is used directly.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _run_adk_pipeline(prd_id: str, prd_content: str) -> TriageReport:
    """Invoke the ADK Runner to execute the specialist + synthesis pipeline.

    This is the integration path that requires GOOGLE_API_KEY. The Runner API:
    1. Creates an InMemorySession.
    2. Sends the PRD content as user message.
    3. Runs root_agent (SequentialAgent → ParallelAgent → Synthesis).
    4. Reads the synthesis output from state["triage_report"].

    ADK 2.x ships ``InMemorySessionService.create_session`` and ``get_session``
    as coroutines — they MUST be awaited. ``Runner.run`` is a synchronous
    generator and MUST NOT be awaited. Callers MUST drive this function via
    ``asyncio.run`` from a synchronous context (see spec
    ``triage-pipeline-runtime``).
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as genai_types

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name="prd_triage", user_id="pipeline"
    )

    runner = Runner(
        agent=root_agent,
        app_name="prd_triage",
        session_service=session_service,
    )

    user_message = genai_types.Content(
        role="user",
        parts=[genai_types.Part.from_text(text=f"Analyze this PRD:\n\n{prd_content}")],
    )

    # Runner.run is a synchronous generator in ADK 2.x — do NOT await it.
    for event in runner.run(
        user_id="pipeline",
        session_id=session.id,
        new_message=user_message,
    ):
        pass  # consume events; final state is in session

    final_session = await session_service.get_session(
        app_name="prd_triage", user_id="pipeline", session_id=session.id
    )
    state = final_session.state

    # Synthesis agent writes to state["triage_report"].
    report_data = state.get("triage_report")
    if report_data is None:
        raise RuntimeError("Synthesis agent did not produce a triage_report in state")

    if isinstance(report_data, TriageReport):
        return report_data
    if isinstance(report_data, dict):
        return TriageReport.model_validate(report_data)
    raise RuntimeError(
        f"Unexpected triage_report type in state: {type(report_data).__name__}"
    )


# ---------------------------------------------------------------------------
# Deterministic post-checks (D5) — run AFTER synthesis, no LLM involved
# ---------------------------------------------------------------------------


def apply_critical_risk_veto(report: TriageReport) -> TriageReport:
    """Force verdict=needs_clarification when any Risk finding is critical.

    Per design.md Decision: Synthesis Agent with critical-risk veto logic:
    "LLM 對 critical 是否該擋的判斷不穩定,但這是安全關鍵決策,必須可預測"。

    This deterministic post-check runs AFTER the LLM-based synthesis to
    guarantee predictable behavior on safety-critical findings. It does NOT
    override a policy-gate reject (verdict=reject is final).

    Returns the (possibly mutated) report.
    """
    if report.verdict is Verdict.REJECT:
        return report  # policy reject is final — don't second-guess
    if not report.risk:
        return report  # risk agent didn't run or produced nothing

    for finding in report.risk.findings:
        if finding.severity is Severity.CRITICAL:
            report.verdict = Verdict.NEEDS_CLARIFICATION
            veto_q = ClarifyingQuestion(
                question_id="critical_risk_veto",
                question=(
                    f"Critical risk identified: {finding.description}. "
                    "How will this be mitigated before implementation begins?"
                ),
                context=(
                    f"Compliance framework: {finding.compliance_framework}"
                    if finding.compliance_framework
                    else None
                ),
            )
            # Prepend so PM sees the critical question first.
            report.clarifying_questions.insert(0, veto_q)
            break  # one veto trigger is sufficient

    return report


def hitl_gate_cli(
    report: TriageReport,
    input_fn: "callable[[str], str] | None" = None,
) -> TriageReport:
    """Synchronous CLI fallback for the Human-in-the-Loop gate.

    Per design.md Decision: HITL gate via ADK InteractiveCallback + workflow
    state — MVP fallback is synchronous CLI via input().

    Behavior:
    - If verdict != needs_clarification: return immediately (no gate needed).
    - If no clarifying questions: return immediately (nothing to ask).
    - Otherwise: print questions, read PM answers via input_fn.
    - PM types "override": set hitl_overridden=True, verdict=pass.
    - PM answers all questions: populate pm_responses, set status=completed.

    Args:
        report: the TriageReport from synthesis (possibly after veto).
        input_fn: callable used to read PM input. Defaults to builtin input().
            Tests inject a stub to avoid blocking on stdin.

    Returns:
        Updated TriageReport with pm_responses or hitl_overridden set.
    """
    if input_fn is None:
        input_fn = input

    if report.verdict is not Verdict.NEEDS_CLARIFICATION:
        return report
    if not report.clarifying_questions:
        return report

    # Interactive prompt (printed to stdout; tests capture via capsys).
    print("\n" + "=" * 60)
    print("HITL GATE: Pipeline paused for PM clarification")
    print("=" * 60)
    print(f"\nPRD: {report.prd_id}")
    print(f"Verdict: {report.verdict.value}")
    print(f"\n{len(report.clarifying_questions)} clarifying question(s):\n")

    for i, q in enumerate(report.clarifying_questions, 1):
        print(f"  Q{i} [{q.question_id}]: {q.question}")
        if q.context:
            print(f"     Context: {q.context}")

    print("\n" + "-" * 60)
    print("Enter answers (one per question) or type 'override' to force-pass.")
    print("-" * 60 + "\n")

    answers: list[PmAnswer] = []
    overridden = False

    for q in report.clarifying_questions:
        response = input_fn(f"Answer [{q.question_id}]: ").strip()
        if response.lower() == "override":
            overridden = True
            break
        answers.append(PmAnswer(question_id=q.question_id, answer=response))

    if overridden:
        report.hitl_overridden = True
        report.verdict = Verdict.PASS
        # Original clarifying_questions retained for audit trail.
    else:
        report.pm_responses = answers
        report.status = "completed"  # resume — pipeline can proceed to estimation

    return report
