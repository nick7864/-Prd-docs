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
        assert "HITL GATE" in captured.out
        assert "Define latency?" in captured.out
        assert "override" in captured.out.lower()
