"""Markdown report formatter for TriageReport.

Per spec D4.3: "Pipeline SHALL emit a structured Markdown report" at \
`reports/<prd_id>-<timestamp>.md` containing all eight sections: verdict, risk \
register, completeness, clarifying questions, PM responses, estimate, tickets, \
audit trail.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models.schemas import TriageReport

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def format_report(report: TriageReport) -> str:
    """Format a TriageReport as structured Markdown (8 sections per spec)."""
    lines: list[str] = [
        f"# PRD Triage Report: {report.prd_id}",
        "",
        f"**Verdict**: `{report.verdict.value}`  ",
        f"**Status**: `{report.status}`  ",
        f"**Generated**: {datetime.now().isoformat(timespec='seconds')}  ",
        f"**HITL overridden**: {report.hitl_overridden}",
        "",
        "---",
        "",
    ]

    # Section 1: Policy Decision
    if report.policy_decision:
        lines.append("## 1. Policy Gate")
        if report.policy_decision.allowed:
            lines.append("✅ PRD passed policy check (no PII or secrets detected).")
        else:
            lines.append("🚫 PRD **rejected** — policy violations found:")
            lines.append("")
            lines.append("| Type | Matched Pattern | Line |")
            lines.append("|---|---|---|")
            for v in report.policy_decision.violations:
                pat = v.pattern[:40] + ("..." if len(v.pattern) > 40 else "")
                lines.append(f"| `{v.type}` | `{pat}` | {v.line_number or '—'} |")
        lines.append("")

    # Section 2: Completeness
    lines.append("## 2. Completeness Assessment")
    if report.completeness:
        lines.append(f"**Score**: {report.completeness.completeness_score}/100")
        lines.append("")
        if report.completeness.missing_sections:
            lines.append("| Missing Section | Severity |")
            lines.append("|---|---|")
            for s in report.completeness.missing_sections:
                lines.append(f"| {s.section} | `{s.severity.value}` |")
        else:
            lines.append("_All required sections present._")
        if report.completeness.raw_analysis:
            lines.append("")
            lines.append(f"<details><summary>Raw analysis</summary>")
            lines.append("")
            lines.append(report.completeness.raw_analysis)
            lines.append("")
            lines.append("</details>")
    else:
        lines.append("_Not reached (specialist agents did not run)._")
    lines.append("")

    # Section 3: Clarity
    lines.append("## 3. Clarity Assessment")
    if report.clarity:
        if report.clarity.ambiguous_items:
            lines.append("| Phrase | Type | Clarifying Question |")
            lines.append("|---|---|---|")
            for item in report.clarity.ambiguous_items:
                lines.append(
                    f"| {item.phrase} | `{item.type}` | {item.generated_question} |"
                )
        else:
            lines.append("_No ambiguous terms detected._")
    else:
        lines.append("_Not reached._")
    lines.append("")

    # Section 4: Risk Register (consolidated)
    lines.append("## 4. Risk Register")
    if report.risk_register:
        lines.append("| Description | Severity |")
        lines.append("|---|---|")
        for f in report.risk_register:
            lines.append(f"| {f.description} | `{f.severity.value}` |")
    elif report.risk:
        lines.append("| Description | Severity | Framework |")
        lines.append("|---|---|---|")
        for f in report.risk.findings:
            lines.append(
                f"| {f.description} | `{f.severity.value}` | "
                f"{f.compliance_framework or '—'} |"
            )
    else:
        lines.append("_No risks identified (risk agent not active in MVP)._")
    lines.append("")

    # Section 5: Clarifying Questions
    lines.append("## 5. Clarifying Questions for PM")
    if report.clarifying_questions:
        for q in report.clarifying_questions:
            lines.append(f"- **{q.question_id}**: {q.question}")
            if q.context:
                lines.append(f"  - _Context_: {q.context}")
    else:
        lines.append("_No clarifying questions._")
    lines.append("")

    # Section 6: PM Responses
    lines.append("## 6. PM Responses")
    if report.pm_responses:
        for a in report.pm_responses:
            lines.append(f"- **{a.question_id}**: {a.answer}")
    else:
        lines.append("_No PM responses (HITL gate not triggered or still pending)._")
    lines.append("")

    # Section 7: Effort Estimate
    lines.append("## 7. Effort Estimate")
    if report.estimate:
        ci = report.estimate.confidence_interval
        lines.append(f"- **Point estimate**: {report.estimate.point_estimate_days} engineer-days")
        lines.append(
            f"- **Confidence interval**: {ci.low} — {ci.median} — {ci.high} days"
        )
        if report.estimate.low_confidence:
            lines.append("- ⚠️ **Low confidence** (no historical analogues available)")
        if report.estimate.drivers:
            lines.append(f"- **Drivers**: {', '.join(report.estimate.drivers)}")
    else:
        lines.append("_Not reached (estimation agent not active or pipeline terminated)._")
    lines.append("")

    # Section 8: Task Breakdown
    lines.append("## 8. Task Breakdown")
    if report.tickets:
        for t in report.tickets:
            lines.append(f"### {t.title}")
            lines.append(f"- **Effort**: {t.estimated_effort_days} days")
            lines.append(f"- **Description**: {t.description}")
            if t.acceptance_criteria:
                lines.append("- **Acceptance criteria**:")
                for ac in t.acceptance_criteria:
                    lines.append(f"  - {ac}")
            if t.dependencies:
                lines.append(f"- **Depends on**: {', '.join(t.dependencies)}")
            lines.append("")
    else:
        lines.append("_Not reached (breakdown agent not active or pipeline terminated)._")
    lines.append("")

    # Audit Trail (always present)
    lines.append("## Audit Trail")
    lines.append("| Stage | Status | Agent | Error |")
    lines.append("|---|---|---|---|")
    for entry in report.audit_trail:
        agent = entry.agent_name or "—"
        err = entry.error or "—"
        if len(err) > 60:
            err = err[:57] + "..."
        lines.append(
            f"| {entry.stage} | `{entry.status}` | {agent} | {err} |"
        )
    lines.append("")

    # Failed agents
    if report.failed_agents:
        lines.append("## Failed Agents")
        for f in report.failed_agents:
            lines.append(f"- **{f.agent_name}**: {f.error}")
        lines.append("")

    return "\n".join(lines)


def write_report(
    report: TriageReport, output_dir: Path = REPORTS_DIR
) -> Path:
    """Write the TriageReport as a Markdown file and return the path.

    Output: ``reports/<prd_id>-<YYYYMMDD-HHMMSS>.md``
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{report.prd_id}-{timestamp}.md"
    filepath = output_dir / filename
    filepath.write_text(format_report(report), encoding="utf-8")
    return filepath
