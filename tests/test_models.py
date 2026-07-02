"""Round-trip serialization tests for all Pydantic schemas.

Per spec D3.1 verification:
    `pytest tests/test_models.py` confirms schemas serialize/deserialize
    round-trip correctly.
"""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from models.schemas import (  # noqa: E402
    AmbiguousItem,
    ArchitectureConflict,
    ArchitectureReport,
    AuditEntry,
    ClarifyingQuestion,
    ClarityReport,
    CompletenessReport,
    ConfidenceInterval,
    Estimate,
    FailedReport,
    Finding,
    IntegrationPoint,
    MissingSection,
    PmAnswer,
    PolicyDecision,
    PolicyViolation,
    RiskFinding,
    RiskReport,
    Severity,
    Ticket,
    TriageReport,
    Verdict,
)


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


def test_severity_values():
    assert Severity("critical") is Severity.CRITICAL
    assert Severity("low").value == "low"


def test_verdict_values():
    assert Verdict("needs_clarification") is Verdict.NEEDS_CLARIFICATION
    assert Verdict("pass").value == "pass"


# ---------------------------------------------------------------------------
# PolicyDecision
# ---------------------------------------------------------------------------


def test_policy_decision_allows_clean():
    d = PolicyDecision(allowed=True)
    assert d.violations == []
    assert d.model_dump()["allowed"] is True


def test_policy_decision_with_violations_round_trip():
    d = PolicyDecision(
        allowed=False,
        violations=[
            PolicyViolation(type="google_api_key", pattern="AIzaSy...", line_number=8),
            PolicyViolation(type="email", pattern="a@b.com", line_number=12),
        ],
    )
    payload = d.model_dump()
    d2 = PolicyDecision.model_validate(payload)
    assert d2.allowed is False
    assert len(d2.violations) == 2
    assert d2.violations[0].line_number == 8


# ---------------------------------------------------------------------------
# CompletenessReport
# ---------------------------------------------------------------------------


def test_completeness_report_round_trip():
    r = CompletenessReport(
        completeness_score=45,
        missing_sections=[
            MissingSection(section="acceptance_criteria", severity=Severity.HIGH)
        ],
        raw_analysis="Missing Given/When/Then scenarios.",
    )
    payload = r.model_dump()
    r2 = CompletenessReport.model_validate(payload)
    assert r2.completeness_score == 45
    assert r2.missing_sections[0].section == "acceptance_criteria"
    assert r2.missing_sections[0].severity is Severity.HIGH
    assert r2.agent_name == "completeness"


def test_completeness_score_bounds():
    """Score must be 0-100."""
    with pytest.raises(Exception):
        CompletenessReport(completeness_score=150)
    with pytest.raises(Exception):
        CompletenessReport(completeness_score=-1)


# ---------------------------------------------------------------------------
# ClarityReport
# ---------------------------------------------------------------------------


def test_clarity_report_round_trip():
    r = ClarityReport(
        ambiguous_items=[
            AmbiguousItem(
                phrase="fast",
                type="vague_quantifier",
                generated_question="Define target p95 latency (ms)",
            ),
            AmbiguousItem(
                phrase="scalable",
                type="vague_quantifier",
                generated_question="Define expected QPS at peak",
            ),
        ]
    )
    payload = r.model_dump()
    r2 = ClarityReport.model_validate(payload)
    assert len(r2.ambiguous_items) == 2
    assert r2.ambiguous_items[0].phrase == "fast"
    assert r2.ambiguous_items[0].generated_question.startswith("Define")


def test_clarity_report_empty_default():
    r = ClarityReport()
    assert r.ambiguous_items == []
    assert r.agent_name == "clarity"


# ---------------------------------------------------------------------------
# ArchitectureReport + RiskReport
# ---------------------------------------------------------------------------


def test_architecture_report_round_trip():
    r = ArchitectureReport(
        conflicts=[
            ArchitectureConflict(
                description="PRD proposes new payment service; ADR-001 splits by capability",
                severity=Severity.MEDIUM,
            )
        ],
        integration_points=[
            IntegrationPoint(description="Calls order-svc", service="order-svc"),
        ],
    )
    r2 = ArchitectureReport.model_validate(r.model_dump())
    assert r2.conflicts[0].severity is Severity.MEDIUM
    assert r2.integration_points[0].service == "order-svc"


def test_risk_report_round_trip():
    r = RiskReport(
        findings=[
            RiskFinding(
                description="Collecting emails without retention policy",
                severity=Severity.HIGH,
                compliance_framework="GDPR",
            ),
            RiskFinding(
                description="Critical: payment data flowing through logs",
                severity=Severity.CRITICAL,
                compliance_framework="PCI-DSS",
            ),
        ]
    )
    r2 = RiskReport.model_validate(r.model_dump())
    assert r2.findings[1].severity is Severity.CRITICAL
    assert r2.findings[0].compliance_framework == "GDPR"


# ---------------------------------------------------------------------------
# FailedReport (orchestrator fallback)
# ---------------------------------------------------------------------------


def test_failed_report():
    r = FailedReport(agent_name="architecture", error="LLM timeout")
    assert r.status == "failed"
    assert r.agent_name == "architecture"


# ---------------------------------------------------------------------------
# HITL: ClarifyingQuestion + PmAnswer
# ---------------------------------------------------------------------------


def test_clarifying_question_and_answer():
    q = ClarifyingQuestion(
        question_id="q1", question="Define 'fast'", context="Section 3.2 NFR"
    )
    a = PmAnswer(question_id="q1", answer="p95 < 200ms")
    assert q.question_id == a.question_id


# ---------------------------------------------------------------------------
# Estimate + Ticket (D7)
# ---------------------------------------------------------------------------


def test_estimate_round_trip():
    e = Estimate(
        point_estimate_days=10.0,
        confidence_interval=ConfidenceInterval(low=6.0, median=10.0, high=15.0),
        drivers=["new payment integration", "no historical analogue"],
        low_confidence=False,
    )
    e2 = Estimate.model_validate(e.model_dump())
    assert e2.confidence_interval.high == 15.0


def test_ticket_dependencies():
    t = Ticket(
        title="Setup Stripe webhook",
        description="Create webhook endpoint",
        acceptance_criteria=["Webhook returns 200", "Signature verified"],
        estimated_effort_days=2.0,
        dependencies=["Design DB schema"],
    )
    t2 = Ticket.model_validate(t.model_dump())
    assert t2.dependencies == ["Design DB schema"]


# ---------------------------------------------------------------------------
# TriageReport composite
# ---------------------------------------------------------------------------


def test_triage_report_minimal():
    """Minimal TriageReport only requires prd_id + verdict."""
    r = TriageReport(prd_id="prd-001", verdict=Verdict.PASS)
    assert r.status == "completed"
    assert r.hitl_overridden is False
    assert r.failed_agents == []


def test_triage_report_full_round_trip():
    """Full report with all stages populated round-trips cleanly."""
    r = TriageReport(
        prd_id="prd-003",
        verdict=Verdict.REJECT,
        status="completed",
        completeness=CompletenessReport(completeness_score=70),
        risk=RiskReport(
            findings=[
                RiskFinding(
                    description="Exposed API key",
                    severity=Severity.CRITICAL,
                    compliance_framework="secret_exposure",
                )
            ]
        ),
        failed_agents=[FailedReport(agent_name="architecture", error="timeout")],
        risk_register=[
            Finding(description="Exposed API key", severity=Severity.CRITICAL)
        ],
        audit_trail=[
            AuditEntry(stage="intake", status="completed"),
            AuditEntry(stage="policy", status="completed"),
            AuditEntry(
                stage="specialist",
                status="failed",
                agent_name="architecture",
                error="timeout",
            ),
        ],
        policy_decision=PolicyDecision(
            allowed=False,
            violations=[
                PolicyViolation(
                    type="google_api_key",
                    pattern="AIzaSy...",
                    line_number=8,
                )
            ],
        ),
    )
    payload = r.model_dump()
    r2 = TriageReport.model_validate(payload)
    assert r2.verdict is Verdict.REJECT
    assert r2.risk.findings[0].compliance_framework == "secret_exposure"
    assert r2.failed_agents[0].agent_name == "architecture"
    assert r2.policy_decision.violations[0].type == "google_api_key"
    assert r2.estimate is None  # pipeline rejected before estimation


def test_triage_report_awaiting_pm_state():
    """HITL pause yields status='awaiting_pm' with no estimate."""
    r = TriageReport(
        prd_id="prd-004",
        verdict=Verdict.NEEDS_CLARIFICATION,
        status="awaiting_pm",
        clarifying_questions=[
            ClarifyingQuestion(question_id="q1", question="Define 'fast'")
        ],
    )
    assert r.status == "awaiting_pm"
    assert r.estimate is None
    assert r.tickets == []


def test_triage_report_json_serialization():
    """model_dump_json produces valid JSON that re-validates."""
    import json

    r = TriageReport(prd_id="x", verdict=Verdict.PASS)
    blob = r.model_dump_json()
    parsed = json.loads(blob)
    assert parsed["verdict"] == "pass"
    r2 = TriageReport.model_validate_json(blob)
    assert r2.prd_id == "x"
