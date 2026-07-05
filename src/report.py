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
        f"# PRD 審查報告：{report.prd_id}",
        "",
        f"**判斷**：`{report.verdict.value}`  ",
        f"**狀態**：`{report.status}`  ",
        f"**產生時間**：{datetime.now().isoformat(timespec='seconds')}  ",
        f"**HITL 已覆寫**：{report.hitl_overridden}",
        "",
        "---",
        "",
    ]

    # Section 1: Policy Decision
    if report.policy_decision:
        lines.append("## 1. 政策閘門")
        if report.policy_decision.allowed:
            lines.append("✅ PRD 通過政策檢查（未偵測到 PII 或金鑰）。")
        else:
            lines.append("🚫 PRD **已駁回** —— 偵測到政策違規：")
            lines.append("")
            lines.append("| 類型 | 符合的模式 | 行號 |")
            lines.append("|---|---|---|")
            for v in report.policy_decision.violations:
                pat = v.pattern[:40] + ("..." if len(v.pattern) > 40 else "")
                lines.append(f"| `{v.type}` | `{pat}` | {v.line_number or '—'} |")
        lines.append("")

    # Section 2: Completeness
    lines.append("## 2. 完整性評估")
    if report.completeness:
        lines.append(f"**分數**：{report.completeness.completeness_score}/100")
        lines.append("")
        if report.completeness.missing_sections:
            lines.append("| 缺失章節 | 嚴重度 |")
            lines.append("|---|---|")
            for s in report.completeness.missing_sections:
                lines.append(f"| {s.section} | `{s.severity.value}` |")
        else:
            lines.append("_所有必要章節齊全。_")
        if report.completeness.raw_analysis:
            lines.append("")
            lines.append(f"<details><summary>原始分析</summary>")
            lines.append("")
            lines.append(report.completeness.raw_analysis)
            lines.append("")
            lines.append("</details>")
    else:
        lines.append("_未執行（專家代理人未運行）。_")
    lines.append("")

    # Section 3: Clarity
    lines.append("## 3. 清晰度評估")
    if report.clarity:
        if report.clarity.ambiguous_items:
            lines.append("| 模糊詞彙 | 類型 | 釐清問題 |")
            lines.append("|---|---|---|")
            for item in report.clarity.ambiguous_items:
                lines.append(
                    f"| {item.phrase} | `{item.type}` | {item.generated_question} |"
                )
        else:
            lines.append("_未偵測到模糊詞彙。_")
    else:
        lines.append("_未執行。_")
    lines.append("")

    # Section 4: Risk Register (consolidated)
    lines.append("## 4. 風險登記表")
    if report.risk_register:
        lines.append("| 描述 | 嚴重度 |")
        lines.append("|---|---|")
        for f in report.risk_register:
            lines.append(f"| {f.description} | `{f.severity.value}` |")
    elif report.risk:
        lines.append("| 描述 | 嚴重度 | 框架 |")
        lines.append("|---|---|---|")
        for f in report.risk.findings:
            lines.append(
                f"| {f.description} | `{f.severity.value}` | "
                f"{f.compliance_framework or '—'} |"
            )
    else:
        lines.append("_未識別出風險（風險代理人未啟用）。_")
    lines.append("")

    # Section 5: Clarifying Questions
    lines.append("## 5. 待 PM 釐清的問題")
    if report.clarifying_questions:
        for q in report.clarifying_questions:
            lines.append(f"- **{q.question_id}**：{q.question}")
            if q.context:
                lines.append(f"  - _上下文_：{q.context}")
    else:
        lines.append("_無待釐清問題。_")
    lines.append("")

    # Section 6: PM Responses
    lines.append("## 6. PM 回應")
    if report.pm_responses:
        for a in report.pm_responses:
            lines.append(f"- **{a.question_id}**：{a.answer}")
    else:
        lines.append("_無 PM 回應（HITL 閘門未觸發或仍在等待）。_")
    lines.append("")

    # Section 7: Effort Estimate
    lines.append("## 7. 工作量估算")
    if report.estimate:
        ci = report.estimate.confidence_interval
        lines.append(f"- **點估計**：{report.estimate.point_estimate_days} 人天")
        lines.append(
            f"- **信心區間**：{ci.low} — {ci.median} — {ci.high} 天"
        )
        if report.estimate.low_confidence:
            lines.append("- ⚠️ **低信心**（無歷史類比可供參考）")
        if report.estimate.drivers:
            lines.append(f"- **影響因子**：{', '.join(report.estimate.drivers)}")
    else:
        lines.append("_未執行（估算代理人未啟用或流程提前終止）。_")
    lines.append("")

    # Section 8: Task Breakdown
    lines.append("## 8. 任務拆解")
    if report.tickets:
        for t in report.tickets:
            lines.append(f"### {t.title}")
            lines.append(f"- **工作量**：{t.estimated_effort_days} 天")
            lines.append(f"- **說明**：{t.description}")
            if t.acceptance_criteria:
                lines.append("- **驗收條件**：")
                for ac in t.acceptance_criteria:
                    lines.append(f"  - {ac}")
            if t.dependencies:
                lines.append(f"- **依賴於**：{', '.join(t.dependencies)}")
            lines.append("")
    else:
        lines.append("_未執行（拆解代理人未啟用或流程提前終止）。_")
    lines.append("")

    # Audit Trail (always present)
    lines.append("## 審計軌跡")
    lines.append("| 階段 | 狀態 | 代理人 | 錯誤 |")
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
        lines.append("## 失敗的代理人")
        for f in report.failed_agents:
            lines.append(f"- **{f.agent_name}**：{f.error}")
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
