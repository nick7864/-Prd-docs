"""Tests for orchestrator deterministic post-checks: veto + HITL gate.

These exercise the pure-Python logic that runs AFTER the LLM-based synthesis,
requiring no GOOGLE_API_KEY.

Covers:
- D5.5: apply_critical_risk_veto (critical Risk finding → force needs_clarification)
- D5.6: hitl_gate_cli (synchronous CLI pause → PM answers or override)
"""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from agents.orchestrator import apply_critical_risk_veto, hitl_gate_cli  # noqa: E402
from models.schemas import (  # noqa: E402
    ClarifyingQuestion,
    PmAnswer,
    RiskFinding,
    RiskReport,
    Severity,
    TriageReport,
    Verdict,
)

def _report(
    verdict: Verdict = Verdict.PASS,
    risk_findings: list[RiskFinding] | None = None,
    clarifying: list[ClarifyingQuestion] | None = None,
) -> TriageReport:
    """Build a TriageReport with optional risk findings and clarifying questions."""
    return TriageReport(
        prd_id="prd-test",
        verdict=verdict,
        risk=RiskReport(findings=risk_findings or []) if risk_findings is not None else None,
        clarifying_questions=clarifying or [],
    )


# ---------------------------------------------------------------------------
# apply_critical_risk_veto
# ---------------------------------------------------------------------------


class TestCriticalRiskVeto:
    def test_critical_finding_forces_needs_clarification(self):
        """A critical Risk finding overrides a PASS verdict."""
        report = _report(
            verdict=Verdict.PASS,
            risk_findings=[
                RiskFinding(
                    description="Payment data flowing through logs",
                    severity=Severity.CRITICAL,
                    compliance_framework="PCI-DSS",
                )
            ],
        )
        result = apply_critical_risk_veto(report)
        assert result.verdict is Verdict.NEEDS_CLARIFICATION
        assert len(result.clarifying_questions) >= 1
        assert result.clarifying_questions[0].question_id == "critical_risk_veto"
        assert "Payment data" in result.clarifying_questions[0].question

    def test_no_critical_finding_preserves_verdict(self):
        """Non-critical findings do NOT trigger the veto."""
        report = _report(
            verdict=Verdict.PASS,
            risk_findings=[
                RiskFinding(
                    description="Minor input validation gap",
                    severity=Severity.MEDIUM,
                )
            ],
        )
        result = apply_critical_risk_veto(report)
        assert result.verdict is Verdict.PASS
        assert len(result.clarifying_questions) == 0

    def test_reject_verdict_not_overridden(self):
        """Policy-gate reject is final — veto does not change it."""
        report = _report(
            verdict=Verdict.REJECT,
            risk_findings=[
                RiskFinding(
                    description="Critical issue",
                    severity=Severity.CRITICAL,
                )
            ],
        )
        result = apply_critical_risk_veto(report)
        assert result.verdict is Verdict.REJECT

    def test_no_risk_report_no_op(self):
        """When risk agent didn't run, veto is a no-op."""
        report = _report(verdict=Verdict.PASS, risk_findings=None)
        result = apply_critical_risk_veto(report)
        assert result.verdict is Verdict.PASS

    def test_veto_question_has_compliance_context(self):
        """The veto clarifying question references the compliance framework."""
        report = _report(
            verdict=Verdict.PASS,
            risk_findings=[
                RiskFinding(
                    description="GDPR violation",
                    severity=Severity.CRITICAL,
                    compliance_framework="GDPR",
                )
            ],
        )
        result = apply_critical_risk_veto(report)
        assert result.clarifying_questions[0].context is not None
        assert "GDPR" in result.clarifying_questions[0].context

    def test_multiple_critical_findings_single_veto(self):
        """Two critical findings → only one veto question (break after first)."""
        report = _report(
            verdict=Verdict.PASS,
            risk_findings=[
                RiskFinding(description="Critical A", severity=Severity.CRITICAL),
                RiskFinding(description="Critical B", severity=Severity.CRITICAL),
            ],
        )
        result = apply_critical_risk_veto(report)
        veto_qs = [
            q for q in result.clarifying_questions if q.question_id == "critical_risk_veto"
        ]
        assert len(veto_qs) == 1


# ---------------------------------------------------------------------------
# hitl_gate_cli
# ---------------------------------------------------------------------------


class TestHitlGateCli:
    def test_no_gate_on_pass_verdict(self):
        """PASS verdict skips the HITL gate entirely."""
        report = _report(verdict=Verdict.PASS, clarifying=[])
        result = hitl_gate_cli(report, input_fn=lambda _: "")
        assert result is report  # unchanged, returned immediately

    def test_no_gate_on_reject_verdict(self):
        """REJECT verdict skips the HITL gate."""
        report = _report(verdict=Verdict.REJECT)
        result = hitl_gate_cli(report, input_fn=lambda _: "")
        assert result.verdict is Verdict.REJECT

    def test_no_gate_without_clarifying_questions(self):
        """needs_clarification but no questions → no pause."""
        report = _report(verdict=Verdict.NEEDS_CLARIFICATION, clarifying=[])
        result = hitl_gate_cli(report, input_fn=lambda _: "")
        assert result.verdict is Verdict.NEEDS_CLARIFICATION

    def test_pm_answers_collected(self):
        """PM answers all questions → pm_responses populated, status=completed."""
        report = _report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            clarifying=[
                ClarifyingQuestion(question_id="q1", question="Define 'fast'"),
                ClarifyingQuestion(question_id="q2", question="Define 'scalable'"),
            ],
        )
        answers = iter(["p95 < 200ms", "10000 QPS"])
        result = hitl_gate_cli(report, input_fn=lambda prompt: next(answers))

        assert result.verdict is Verdict.NEEDS_CLARIFICATION  # not overridden
        assert result.status == "completed"
        assert len(result.pm_responses) == 2
        assert result.pm_responses[0].question_id == "q1"
        assert result.pm_responses[0].answer == "p95 < 200ms"
        assert result.pm_responses[1].answer == "10000 QPS"

    def test_pm_override_forces_pass(self):
        """PM types 'override' → hitl_overridden=True, verdict=pass."""
        report = _report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            clarifying=[
                ClarifyingQuestion(question_id="q1", question="Define 'fast'"),
                ClarifyingQuestion(question_id="q2", question="Define 'scalable'"),
            ],
        )
        result = hitl_gate_cli(report, input_fn=lambda _: "override")

        assert result.hitl_overridden is True
        assert result.verdict is Verdict.PASS
        # Original questions retained for audit
        assert len(result.clarifying_questions) == 2

    def test_pm_override_case_insensitive(self):
        """'Override' and 'OVERRIDE' also trigger the override path."""
        report = _report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            clarifying=[ClarifyingQuestion(question_id="q1", question="Q?")],
        )
        for override_variant in ["Override", "OVERRIDE", "override"]:
            result = hitl_gate_cli(
                _report(
                    verdict=Verdict.NEEDS_CLARIFICATION,
                    clarifying=[ClarifyingQuestion(question_id="q1", question="Q?")],
                ),
                input_fn=lambda _: override_variant,
            )
            assert result.hitl_overridden is True, f"Failed for variant: {override_variant}"

    def test_gate_prints_prompt(self, capsys):
        """The HITL prompt is printed to stdout (for video demo visibility)."""
        report = _report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            clarifying=[ClarifyingQuestion(question_id="q1", question="Define latency?")],
        )
        hitl_gate_cli(report, input_fn=lambda _: "200ms")
        captured = capsys.readouterr()
        assert "HITL 閘門" in captured.out
        assert "Define latency?" in captured.out
        assert "override" in captured.out.lower()


# ---------------------------------------------------------------------------
# triage / start_triage / resume_triage (HITL session entry points)
#
# These mock _run_pipeline (and _intake for PRD content) so the HITL pause/
# resume logic is exercised without GOOGLE_API_KEY or the ADK Runner.
# ---------------------------------------------------------------------------

from agents import orchestrator  # noqa: E402
from agents.orchestrator import (  # noqa: E402
    get_session_registry,
    resume_triage,
    start_triage,
    triage,
)
from models.schemas import PolicyDecision, SessionNotFound  # noqa: E402
from sessions.registry import SessionRegistry  # noqa: E402


def _pipeline_report(
    verdict: Verdict = Verdict.PASS,
    status: str = "completed",
    clarifying: list[ClarifyingQuestion] | None = None,
) -> TriageReport:
    return TriageReport(
        prd_id="prd-test",
        verdict=verdict,
        status=status,
        clarifying_questions=clarifying or [],
        policy_decision=PolicyDecision(allowed=True),
    )


@pytest.fixture
def isolated_registry(monkeypatch):
    """Give each test a fresh registry swapped into the orchestrator module."""
    reg = SessionRegistry()
    monkeypatch.setattr(orchestrator, "_session_registry", reg)
    return reg


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Stub _run_pipeline and _intake; return a mutable holder for the report.

    Usage: set ``stub_pipeline.report = _pipeline_report(...)`` before calling
    start_triage/triage. ``_intake`` returns a canned PRD with content.
    """
    holder = {"report": _pipeline_report()}

    def fake_run_pipeline(prd_id):
        return holder["report"]

    def fake_intake(prd_id):
        return {"id": prd_id, "content": "canned PRD content", "metadata": {}}

    monkeypatch.setattr(orchestrator, "_run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(orchestrator, "_intake", fake_intake)
    return holder


class TestTriageNonInteractive:
    def test_triage_does_not_create_session(self, isolated_registry, stub_pipeline):
        """triage() is non-interactive: even with clarifying questions it must
        not pause, create a session, or set session_id."""
        stub_pipeline["report"] = _pipeline_report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="completed",
            clarifying=[
                ClarifyingQuestion(question_id="q1", question="Define 'fast'"),
                ClarifyingQuestion(question_id="q2", question="Define 'scalable'"),
            ],
        )
        report = triage("prd-002")
        assert report.session_id is None
        assert report.status == "completed"
        assert get_session_registry() is isolated_registry
        assert isolated_registry.cleanup_expired() == 0


class TestStartTriage:
    def test_start_triage_pauses_on_clarifying_questions(
        self, isolated_registry, stub_pipeline
    ):
        stub_pipeline["report"] = _pipeline_report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="completed",
            clarifying=[
                ClarifyingQuestion(question_id="q1", question="Define 'fast'"),
                ClarifyingQuestion(question_id="q2", question="Define 'scalable'"),
            ],
        )
        report, session_id = start_triage("prd-002")
        assert report.status == "awaiting_pm"
        assert session_id is not None
        assert report.session_id == session_id
        state = isolated_registry.get(session_id)
        assert state is not None
        assert state.prd_id == "prd-002"

    def test_start_triage_pass_returns_no_session(self, isolated_registry, stub_pipeline):
        stub_pipeline["report"] = _pipeline_report(
            verdict=Verdict.PASS, status="completed", clarifying=[]
        )
        report, session_id = start_triage("prd-001")
        assert session_id is None
        assert report.status == "completed"
        assert report.session_id is None

    def test_start_triage_reject_returns_no_session(self, isolated_registry, stub_pipeline):
        stub_pipeline["report"] = _pipeline_report(
            verdict=Verdict.REJECT, status="terminated", clarifying=[]
        )
        report, session_id = start_triage("prd-003")
        assert session_id is None
        assert report.verdict is Verdict.REJECT
        assert report.status == "terminated"


class TestResumeTriage:
    def test_resume_triage_completes_report(self, isolated_registry, stub_pipeline):
        stub_pipeline["report"] = _pipeline_report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="completed",
            clarifying=[
                ClarifyingQuestion(question_id="q1", question="Define 'fast'"),
                ClarifyingQuestion(question_id="q2", question="Define 'scalable'"),
            ],
        )
        _, session_id = start_triage("prd-002")

        result = resume_triage(
            session_id,
            [PmAnswer(question_id="q1", answer="p95 < 200ms")],
        )
        assert result.status == "completed"
        assert result.verdict is Verdict.NEEDS_CLARIFICATION  # unchanged
        assert result.hitl_overridden is False
        assert len(result.pm_responses) == 1
        assert result.pm_responses[0].answer == "p95 < 200ms"
        assert result.session_id is None
        assert isolated_registry.get(session_id) is None

    def test_resume_triage_override_upgrades_verdict(
        self, isolated_registry, stub_pipeline
    ):
        stub_pipeline["report"] = _pipeline_report(
            verdict=Verdict.NEEDS_CLARIFICATION,
            status="completed",
            clarifying=[ClarifyingQuestion(question_id="q1", question="Q?")],
        )
        _, session_id = start_triage("prd-002")

        result = resume_triage(session_id, [], override=True)
        assert result.verdict is Verdict.PASS
        assert result.hitl_overridden is True
        assert result.status == "completed"

    def test_resume_unknown_session_raises(self, isolated_registry, stub_pipeline):
        with pytest.raises(SessionNotFound):
            resume_triage("nonexistent-session", [])


# ---------------------------------------------------------------------------
# Deterministic assembly (fix-synthesis-state)
# ---------------------------------------------------------------------------

from agents.orchestrator import (  # noqa: E402
    _assemble_report,
    _collect_questions,
    _compute_verdict,
    _parse,
)
from models.schemas import (  # noqa: E402
    ArchitectureConflict,
    ArchitectureReport,
    AuditEntry,
    ClarityReport,
    CompletenessReport,
    MissingSection,
    RiskFinding,
    RiskReport,
    SynthesisOutput,
)
from models.schemas import AmbiguousItem  # noqa: E402


def _completeness(score: int) -> CompletenessReport:
    return CompletenessReport(
        agent_name="completeness",
        completeness_score=score,
        missing_sections=[],
        raw_analysis="",
    )


def _clarity(n_questions: int) -> ClarityReport:
    return ClarityReport(
        agent_name="clarity",
        ambiguous_items=[
            AmbiguousItem(phrase=f"term{i}", type="vague_quantifier",
                          generated_question=f"Define term{i}?")
            for i in range(n_questions)
        ],
        raw_analysis="",
    )


class TestParse:
    def test_parse_tolerates_dict_model_and_none(self):
        m = _completeness(80)
        assert _parse(m, CompletenessReport) is m
        assert _parse({"completeness_score": 80, "missing_sections": []},
                      CompletenessReport).completeness_score == 80
        assert _parse(None, CompletenessReport) is None
        # Non-JSON string -> None.
        assert _parse("not a dict", CompletenessReport) is None
        # JSON string (the form _prepare_synthesis_inputs leaves in state after
        # re-serializing specialist dicts for the synthesis prompt) -> parsed.
        assert _parse(
            '{"completeness_score": 80, "missing_sections": []}',
            CompletenessReport,
        ).completeness_score == 80
        # Malformed JSON string -> None.
        assert _parse('{"completeness_score": 80,', CompletenessReport) is None
        # Malformed dict (fails validation) -> None, not raise.
        assert _parse({"completeness_score": "not-an-int"}, CompletenessReport) is None


class TestComputeVerdict:
    def test_compute_verdict_pass_rule(self):
        verdict, _ = _compute_verdict(_completeness(85), _clarity(1))
        assert verdict is Verdict.PASS

    def test_compute_verdict_needs_clarification_on_low_score(self):
        verdict, reason = _compute_verdict(_completeness(40), _clarity(0))
        assert verdict is Verdict.NEEDS_CLARIFICATION
        assert "40" in reason

    def test_compute_verdict_needs_clarification_on_many_questions(self):
        verdict, _ = _compute_verdict(_completeness(85), _clarity(3))
        assert verdict is Verdict.NEEDS_CLARIFICATION

    def test_compute_verdict_missing_completeness_counts_as_zero(self):
        verdict, _ = _compute_verdict(None, _clarity(0))
        assert verdict is Verdict.NEEDS_CLARIFICATION


class TestAssembleReport:
    def test_assemble_report_without_synthesis_returns_valid_report(self):
        audit: list[AuditEntry] = [AuditEntry(stage="intake", status="completed")]
        report = _assemble_report(
            "prd-001", _completeness(85), _clarity(1), None, None, None, audit,
        )
        # Verdict by rule, not LLM (synth was None).
        assert report.verdict is Verdict.PASS
        assert report.status == "completed"
        assert report.prd_id == "prd-001"
        # Graceful degradation: synthesis failure recorded, no exception.
        stages = [(e.stage, e.status) for e in report.audit_trail]
        assert ("specialists", "completed") in stages
        assert ("synthesis", "failed") in stages

    def test_llm_verdict_disagreement_overridden_and_recorded(self):
        audit: list[AuditEntry] = [AuditEntry(stage="intake", status="completed")]
        synth = SynthesisOutput(verdict=Verdict.PASS, raw_analysis="looks fine")
        # Rule says NEEDS_CLARIFICATION (score 40); LLM said PASS -> rule wins.
        report = _assemble_report(
            "prd-002", _completeness(40), _clarity(2), None, None, synth, audit,
        )
        assert report.verdict is Verdict.NEEDS_CLARIFICATION
        disagreements = [
            e for e in report.audit_trail
            if e.stage == "synthesis" and e.error and "LLM 建議" in e.error
        ]
        assert len(disagreements) == 1
        assert "pass" in disagreements[0].error
        assert "needs_clarification" in disagreements[0].error

    def test_critical_risk_veto_invoked_during_assembly(self):
        audit: list[AuditEntry] = [AuditEntry(stage="intake", status="completed")]
        risk = RiskReport(
            agent_name="risk",
            findings=[RiskFinding(
                description="Payment data in logs",
                severity=Severity.CRITICAL,
                compliance_framework="PCI-DSS",
            )],
            raw_analysis="",
        )
        # Rule would say PASS (score 85), but critical risk must veto.
        report = _assemble_report(
            "prd-003", _completeness(85), _clarity(0), None, risk,
            SynthesisOutput(verdict=Verdict.PASS), audit,
        )
        assert report.verdict is Verdict.NEEDS_CLARIFICATION
        ids = [q.question_id for q in report.clarifying_questions]
        assert "critical_risk_veto" in ids

    def test_assemble_report_collects_clarity_questions(self):
        audit: list[AuditEntry] = []
        report = _assemble_report(
            "prd-004", _completeness(40), _clarity(2), None, None, None, audit,
        )
        ids = [q.question_id for q in report.clarifying_questions]
        assert "clarity_0" in ids and "clarity_1" in ids

    def test_assemble_report_collects_high_architecture_conflicts(self):
        audit: list[AuditEntry] = []
        arch = ArchitectureReport(
            agent_name="architecture",
            conflicts=[ArchitectureConflict(
                description="Needs new microservice", severity=Severity.HIGH)],
            integration_points=[],
            raw_analysis="",
        )
        report = _assemble_report(
            "prd-005", _completeness(85), _clarity(0), arch, None, None, audit,
        )
        ids = [q.question_id for q in report.clarifying_questions]
        assert "arch_0" in ids


class TestCollectQuestions:
    def test_collect_dedupes_by_question_id(self):
        clarity = _clarity(1)
        synth = SynthesisOutput(
            verdict=Verdict.NEEDS_CLARIFICATION,
            clarifying_questions=[
                ClarifyingQuestion(question_id="clarity_0", question="dup"),
            ],
        )
        qs = _collect_questions(clarity, None, synth)
        ids = [q.question_id for q in qs]
        assert ids.count("clarity_0") == 1
