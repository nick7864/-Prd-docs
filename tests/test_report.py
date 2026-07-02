"""Tests for the Markdown report formatter (src/report.py)."""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from models.schemas import (  # noqa: E402
    AuditEntry,
    ClarifyingQuestion,
    CompletenessReport,
    ConfidenceInterval,
    Estimate,
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
from report import format_report, write_report  # noqa: E402

# NOTE: The API key in the test fixture below (AIzaSyDabc123...) is a FAKE test
# fixture for verifying report formatting. NOT a real credential.


def _minimal_report() -> TriageReport:
    return TriageReport(
        prd_id="prd-001",
        verdict=Verdict.PASS,
        audit_trail=[
            AuditEntry(stage="intake", status="completed"),
            AuditEntry(stage="policy", status="completed"),
        ],
    )


def _full_report() -> TriageReport:
    return TriageReport(
        prd_id="prd-002",
        verdict=Verdict.NEEDS_CLARIFICATION,
        status="awaiting_pm",
        completeness=CompletenessReport(
            completeness_score=45,
            missing_sections=[
                MissingSection(section="acceptance_criteria", severity=Severity.HIGH)
            ],
            raw_analysis="PRD lacks Given/When/Then scenarios entirely.",
        ),
        risk=RiskReport(
            findings=[
                RiskFinding(
                    description="PII collected without retention policy",
                    severity=Severity.HIGH,
                    compliance_framework="GDPR",
                )
            ]
        ),
        risk_register=[
            RiskFinding(
                description="PII collected without retention policy",
                severity=Severity.HIGH,
                compliance_framework="GDPR",
            )
        ],
        clarifying_questions=[
            ClarifyingQuestion(
                question_id="q1",
                question="Define 'fast' — what is the target p95 latency?",
                context="Section 3: Non-Functional Requirements",
            )
        ],
        pm_responses=[
            PmAnswer(question_id="q1", answer="p95 < 200ms")
        ],
        estimate=Estimate(
            point_estimate_days=8.0,
            confidence_interval=ConfidenceInterval(low=5.0, median=8.0, high=12.0),
            drivers=["new API integration", "no historical analogue for this scope"],
            low_confidence=True,
        ),
        tickets=[
            Ticket(
                title="Design schema",
                description="Create DB tables for the new feature",
                acceptance_criteria=["Tables created", "Migrations pass"],
                estimated_effort_days=2.0,
                dependencies=[],
            ),
            Ticket(
                title="Implement API endpoint",
                description="REST endpoint for the feature",
                acceptance_criteria=["Returns 200", "Handles errors"],
                estimated_effort_days=3.0,
                dependencies=["Design schema"],
            ),
        ],
        audit_trail=[
            AuditEntry(stage="intake", status="completed"),
            AuditEntry(stage="policy", status="completed"),
            AuditEntry(
                stage="specialists",
                status="completed",
                agent_name="completeness_checker",
            ),
            AuditEntry(
                stage="specialists",
                status="completed",
                agent_name="clarity_checker",
            ),
            AuditEntry(stage="synthesis", status="completed"),
        ],
        policy_decision=PolicyDecision(allowed=True),
    )


def _rejected_report() -> TriageReport:
    return TriageReport(
        prd_id="prd-003",
        verdict=Verdict.REJECT,
        status="terminated",
        policy_decision=PolicyDecision(
            allowed=False,
            violations=[
                PolicyViolation(
                    type="google_api_key",
                    pattern="AIzaSyDabc123def456ghi789jkl012mno345pqr",
                    line_number=8,
                )
            ],
        ),
        audit_trail=[
            AuditEntry(stage="intake", status="completed"),
            AuditEntry(
                stage="policy",
                status="completed",
                error="Rejected: ['google_api_key']",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


class TestFormatReportMinimal:
    def test_contains_prd_id(self):
        md = format_report(_minimal_report())
        assert "prd-001" in md

    def test_contains_verdict(self):
        md = format_report(_minimal_report())
        assert "`pass`" in md

    def test_contains_all_eight_section_headings(self):
        """Spec: report SHALL contain all eight sections."""
        md = format_report(_full_report())
        for heading in [
            "## 1. Policy Gate",
            "## 2. Completeness Assessment",
            "## 3. Clarity Assessment",
            "## 4. Risk Register",
            "## 5. Clarifying Questions for PM",
            "## 6. PM Responses",
            "## 7. Effort Estimate",
            "## 8. Task Breakdown",
            "## Audit Trail",
        ]:
            assert heading in md, f"Missing section: {heading}"


class TestFormatReportFull:
    def test_completeness_score_in_output(self):
        md = format_report(_full_report())
        assert "45/100" in md

    def test_missing_section_in_output(self):
        md = format_report(_full_report())
        assert "acceptance_criteria" in md
        assert "`high`" in md

    def test_clarifying_question_in_output(self):
        md = format_report(_full_report())
        assert "q1" in md
        assert "p95 latency" in md

    def test_pm_response_in_output(self):
        md = format_report(_full_report())
        assert "p95 < 200ms" in md

    def test_estimate_in_output(self):
        md = format_report(_full_report())
        assert "8.0 engineer-days" in md
        assert "Low confidence" in md

    def test_tickets_in_output(self):
        md = format_report(_full_report())
        assert "Design schema" in md
        assert "Implement API endpoint" in md
        assert "Depends on" in md

    def test_audit_trail_rows(self):
        md = format_report(_full_report())
        assert "| intake | `completed` |" in md
        assert "| synthesis | `completed` |" in md


class TestFormatReportRejected:
    def test_policy_violation_in_output(self):
        md = format_report(_rejected_report())
        assert "`google_api_key`" in md
        assert "AIzaSy" in md

    def test_rejected_verdict(self):
        md = format_report(_rejected_report())
        assert "`reject`" in md

    def test_no_estimate_section_populated(self):
        md = format_report(_rejected_report())
        assert "Not reached" in md


# ---------------------------------------------------------------------------
# write_report
# ---------------------------------------------------------------------------


class TestWriteReport:
    def test_writes_file_to_reports_dir(self, tmp_path):
        path = write_report(_minimal_report(), output_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".md"
        assert "prd-001" in path.name

    def test_filename_has_timestamp(self, tmp_path):
        path = write_report(_minimal_report(), output_dir=tmp_path)
        # filename format: prd-001-YYYYMMDD-HHMMSS.md
        parts = path.stem.split("-")
        assert len(parts) >= 3  # prd, 001, datestamp

    def test_creates_output_dir_if_missing(self, tmp_path):
        output = tmp_path / "subdir" / "reports"
        path = write_report(_minimal_report(), output_dir=output)
        assert path.exists()
        assert output.exists()

    def test_file_content_is_valid_markdown(self, tmp_path):
        path = write_report(_full_report(), output_dir=tmp_path)
        content = path.read_text()
        assert content.startswith("# PRD Triage Report")
        assert "## Audit Trail" in content
