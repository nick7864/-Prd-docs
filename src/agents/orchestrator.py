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
# bypass the MCP server. override=True so a stale EMPTY value already in the
# environment (e.g. an exported GOOGLE_API_KEY="") cannot shadow the real key
# in .env — otherwise specialists silently get skipped with "key not set".
load_dotenv(override=True)

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent

# Apply the markdown fence-stripping patch for non-Gemini providers (e.g. GLM
# wraps structured JSON in ```json fences; ADK's validate_schema rejects that).
# Imported for its side effect; must come after the google.adk import above.
from . import _schema_fence_patch  # noqa: F401

from doc_mcp.repository import get_prd
from models.schemas import (
    ArchitectureReport,
    AuditEntry,
    ClarifyingQuestion,
    ClarityReport,
    CompletenessReport,
    PmAnswer,
    PolicyDecision,
    RiskReport,
    SessionNotFound,
    SessionState,
    Severity,
    SynthesisOutput,
    TriageReport,
    Verdict,
)
from policy.checker import check_policy
from sessions.registry import SessionRegistry, default_ttl_seconds

from .architecture import architecture_checker
from .clarity import clarity_checker
from .completeness import completeness_checker
from ._model import _has_model_key
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


def _run_pipeline(prd_id: str) -> TriageReport:
    """Run intake → policy → specialists → synthesis and return the report.

    This is the shared pipeline body. The public ``triage()`` is a thin
    non-interactive wrapper over it; ``start_triage()`` calls it then decides
    whether to pause for HITL.
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
                error=f"已駁回：{[v.type for v in decision.violations]}",
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
    if not _has_model_key():
        audit.append(
            AuditEntry(
                stage="specialists",
                status="skipped",
                error="GOOGLE_API_KEY 未設定；無法執行 LLM 代理人",
            )
        )
        return TriageReport(
            prd_id=prd_id,
            verdict=Verdict.PASS,  # optimistic default; real pipeline would analyze
            status="terminated",
            audit_trail=audit,
            policy_decision=decision,
        )

    # Run the ADK pipeline via Runner. _run_adk_pipeline (via _assemble_report)
    # owns the specialists/synthesis audit entries and sets result.audit_trail,
    # so this try block only attaches policy_decision on success.
    try:
        result = _run_coro_safely(_run_adk_pipeline(prd_id, prd["content"], audit))
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


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

# Module-level singleton shared by start_triage/resume_triage and the HTTP layer.
_session_registry = SessionRegistry()


def get_session_registry() -> SessionRegistry:
    """Return the process-wide HITL session registry (shared with HTTP layer)."""
    return _session_registry


def triage(prd_id: str) -> TriageReport:
    """Non-interactive full pipeline run (MCP tool / CLI entry point).

    Runs the full pipeline synchronously and never pauses for human input.
    Behavior is unchanged from before the HITL work: it returns a single
    TriageReport with status ``completed`` or ``terminated``, ``session_id``
    left None, and creates no session.
    """
    return _run_pipeline(prd_id)


def start_triage(prd_id: str) -> tuple[TriageReport, str | None]:
    """Run the pipeline, pausing for HITL when synthesis raises questions.

    Returns ``(report, session_id)``. When the report's verdict is not reject
    AND it carries clarifying questions, the report is stored in the session
    registry, marked ``status="awaiting_pm"`` with its ``session_id`` set, and
    the session id is returned. Otherwise the report is returned with
    ``session_id=None`` (status stays ``completed`` or ``terminated``).
    """
    report = _run_pipeline(prd_id)

    should_pause = (
        report.verdict is not Verdict.REJECT
        and report.status != "terminated"
        and bool(report.clarifying_questions)
    )
    if not should_pause:
        return report, None

    prd = _intake(prd_id)
    prd_content = prd.get("content", "")
    now = datetime.now(timezone.utc)
    state = SessionState(
        prd_id=prd_id,
        prd_content=prd_content,
        policy_decision=report.policy_decision or PolicyDecision(allowed=True),
        partial_report=report,
        created_at=now,
        expires_at=now + timedelta(seconds=default_ttl_seconds()),
    )
    session_id = _session_registry.create(state)
    report.status = "awaiting_pm"
    report.session_id = session_id
    return report, session_id


def resume_triage(
    session_id: str,
    answers: list[PmAnswer],
    override: bool = False,
) -> TriageReport:
    """Finalize a paused report with the PM's answers.

    Raises ``SessionNotFound`` if the session does not exist or has expired.
    Otherwise copies the answers into the report's ``pm_responses``, sets
    ``status="completed"``; when ``override`` is True, additionally sets
    ``hitl_overridden=True`` and ``verdict=pass``. Deletes the session.
    """
    state = _session_registry.get(session_id)
    if state is None:
        raise SessionNotFound(session_id)

    report = state.partial_report
    report.pm_responses = list(answers)
    if override:
        report.hitl_overridden = True
        report.verdict = Verdict.PASS
    report.status = "completed"
    report.session_id = None
    _session_registry.delete(session_id)
    return report


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


# ---------------------------------------------------------------------------
# Deterministic assembly (fix-synthesis-state) — synthesis is advisory; the
# orchestrator owns the final TriageReport, verdict, and audit for the
# specialists/synthesis stages.
# ---------------------------------------------------------------------------


def _parse(raw, model_cls):
    """Tolerantly parse a specialist state value.

    Handles three representations that can appear in ADK session state:
    a validated model instance (passthrough), a dict (``model_validate``),
    or a JSON string (``model_validate_json``). The string form is produced
    by ``_prepare_synthesis_inputs``, which re-serializes specialist dicts
    to JSON strings for synthesis prompt injection; without this branch the
    orchestrator would read those strings AFTER synthesis runs and silently
    lose all specialist data. Returns ``None`` for anything else (None,
    malformed, unexpected types).
    """
    if isinstance(raw, model_cls):
        return raw
    if isinstance(raw, dict):
        try:
            return model_cls.model_validate(raw)
        except Exception:
            return None
    if isinstance(raw, str):
        try:
            return model_cls.model_validate_json(raw)
        except Exception:
            return None
    return None


def _compute_verdict(
    completeness: CompletenessReport | None,
    clarity: ClarityReport | None,
) -> tuple[Verdict, str]:
    """Deterministic verdict per the documented MVP rule.

    PASS when completeness_score >= 80 AND fewer than 3 clarifying questions
    (clarity ambiguities); otherwise NEEDS_CLARIFICATION. A missing
    completeness report counts as score 0. Returns (verdict, reason).
    """
    score = completeness.completeness_score if completeness else 0
    q_count = len(clarity.ambiguous_items) if clarity else 0
    if score >= 80 and q_count < 3:
        return Verdict.PASS, f"分數={score}，問題數={q_count}"
    reasons = []
    if score < 80:
        reasons.append(f"完整度分數={score} < 80")
    if q_count >= 3:
        reasons.append(f"待釐清問題 {q_count} 個 ≥ 3")
    return Verdict.NEEDS_CLARIFICATION, "、".join(reasons)


def _collect_questions(
    clarity: ClarityReport | None,
    architecture: ArchitectureReport | None,
    synth: SynthesisOutput | None,
) -> list[ClarifyingQuestion]:
    """Build the clarifying_questions list from clarity, architecture, synthesis.

    Clarity ambiguities are the primary source (they carry generated_question).
    High/critical architecture conflicts are surfaced as questions. The
    synthesis LLM's own questions are merged in (deduped by question_id).
    """
    collected: list[ClarifyingQuestion] = []
    seen: set[str] = set()

    def _add(q: ClarifyingQuestion) -> None:
        if q.question_id not in seen:
            seen.add(q.question_id)
            collected.append(q)

    if clarity:
        for i, item in enumerate(clarity.ambiguous_items):
            _add(ClarifyingQuestion(
                question_id=f"clarity_{i}",
                question=item.generated_question,
                context=f"模糊詞彙：'{item.phrase}'（{item.type}）",
            ))
    if architecture:
        for i, conflict in enumerate(architecture.conflicts):
            if conflict.severity in (Severity.HIGH, Severity.CRITICAL):
                _add(ClarifyingQuestion(
                    question_id=f"arch_{i}",
                    question=(
                        f"架構衝突（{conflict.severity.value}）："
                        f"{conflict.description} —— 應如何解決？"
                    ),
                ))
    if synth:
        for q in synth.clarifying_questions:
            _add(q)
    return collected


def _assemble_report(
    prd_id: str,
    completeness: CompletenessReport | None,
    clarity: ClarityReport | None,
    architecture: ArchitectureReport | None,
    risk: RiskReport | None,
    synth: SynthesisOutput | None,
    audit: list[AuditEntry],
) -> TriageReport:
    """Deterministically assemble the final TriageReport.

    The orchestrator (not any LLM) sets prd_id, specialist sub-objects,
    clarifying_questions, and audit_trail. Verdict is computed by rule; the
    LLM's suggestion is recorded but does not win. Missing synthesis degrades
    gracefully. ``apply_critical_risk_veto`` is enforced before returning.
    """
    audit.append(AuditEntry(stage="specialists", status="completed"))

    rule_verdict, reason = _compute_verdict(completeness, clarity)
    questions = _collect_questions(clarity, architecture, synth)

    # Append all synthesis audit entries BEFORE constructing the report —
    # Pydantic copies audit_trail on assignment, so later mutations to `audit`
    # would not surface on the report.
    if synth is None:
        audit.append(AuditEntry(
            stage="synthesis",
            status="failed",
            error="synthesis 未產出結果，使用 deterministic 組裝",
        ))
    else:
        audit.append(AuditEntry(stage="synthesis", status="completed"))
        if synth.verdict is not None and synth.verdict != rule_verdict:
            audit.append(AuditEntry(
                stage="synthesis",
                status="completed",
                error=(
                    f"LLM 建議 {synth.verdict.value}，"
                    f"規則採用 {rule_verdict.value}（{reason}）"
                ),
            ))

    report = TriageReport(
        prd_id=prd_id,
        verdict=rule_verdict,
        status="completed",
        completeness=completeness,
        clarity=clarity,
        architecture=architecture,
        risk=risk,
        clarifying_questions=questions,
        audit_trail=audit,
    )

    # Safety veto: a critical risk finding overrides even a rule-PASS.
    return apply_critical_risk_veto(report)


async def _run_adk_pipeline(
    prd_id: str, prd_content: str, audit: list[AuditEntry]
) -> TriageReport:
    """Invoke the ADK Runner to execute the specialist + synthesis pipeline.

    Reads the four specialist outputs and the advisory synthesis output from
    session state and deterministically assembles the final TriageReport via
    ``_assemble_report``. Never raises when synthesis output is absent — that
    degrades gracefully.

    ADK 2.x ships ``InMemorySessionService.create_session`` and ``get_session``
    as coroutines — they MUST be awaited. ``Runner.run`` is a synchronous
    generator and MUST NOT be awaited.
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
        parts=[genai_types.Part.from_text(text=f"請分析以下 PRD：\n\n{prd_content}")],
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

    completeness = _parse(state.get("completeness_report"), CompletenessReport)
    clarity = _parse(state.get("clarity_report"), ClarityReport)
    architecture = _parse(state.get("architecture_report"), ArchitectureReport)
    risk = _parse(state.get("risk_report"), RiskReport)
    synth = _parse(state.get("synthesis_output"), SynthesisOutput)

    return _assemble_report(
        prd_id, completeness, clarity, architecture, risk, synth, audit
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
                    f"已識別嚴重風險：{finding.description}。"
                    "在開始實作前，此風險應如何緩解？"
                ),
                context=(
                    f"合規框架：{finding.compliance_framework}"
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
    print("HITL 閘門：流程已暫停，等待 PM 釐清")
    print("=" * 60)
    print(f"\n需求文件：{report.prd_id}")
    print(f"判斷：{report.verdict.value}")
    print(f"\n共 {len(report.clarifying_questions)} 個待釐清問題：\n")

    for i, q in enumerate(report.clarifying_questions, 1):
        print(f"  問題 {i} [{q.question_id}]: {q.question}")
        if q.context:
            print(f"     上下文：{q.context}")

    print("\n" + "-" * 60)
    print("請輸入回答（每題一行），或輸入 'override' / '覆寫' 直接強制通過。")
    print("-" * 60 + "\n")

    answers: list[PmAnswer] = []
    overridden = False

    for q in report.clarifying_questions:
        response = input_fn(f"回答 [{q.question_id}]: ").strip()
        if response.lower() in ("override", "覆寫"):
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
