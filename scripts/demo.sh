#!/usr/bin/env bash
# Run all 5 demo cases through the PRD Triage pipeline.
# Generates Markdown reports in reports/ for each PRD.
#
# Prerequisites:
#   - GOOGLE_API_KEY exported (for LLM-based agents)
#   - uv sync completed
#
# Usage:
#   export GOOGLE_API_KEY="your-key"
#   bash scripts/demo.sh

set -euo pipefail

echo "=== PRD Triage Demo: 5 cases ==="
echo ""

for id in prd-001 prd-002 prd-003 prd-004 prd-005; do
    echo "--- $id ---"
    uv run python -c "
import sys
sys.path.insert(0, 'src')
from agents.orchestrator import triage
from report import write_report

report = triage('${id}')
path = write_report(report)

print(f'  PRD:      {report.prd_id}')
print(f'  Verdict:  {report.verdict.value}')
print(f'  Status:   {report.status}')

if report.policy_decision and not report.policy_decision.allowed:
    types = [v.type for v in report.policy_decision.violations]
    print(f'  Policy:   REJECTED ({types})')

if report.completeness:
    print(f'  Score:    {report.completeness.completeness_score}/100')
    missing = [s.section for s in report.completeness.missing_sections]
    if missing:
        print(f'  Missing:  {missing}')

if report.clarify_questions if hasattr(report, 'clarify_questions') else report.clarifying_questions:
    n = len(report.clarifying_questions)
    print(f'  Questions: {n} clarifying question(s) for PM')

if report.estimate:
    ci = report.estimate.confidence_interval
    print(f'  Estimate: {report.estimate.point_estimate_days} days ({ci.low}-{ci.high})')

if report.tickets:
    print(f'  Tickets:  {len(report.tickets)} tickets generated')

print(f'  Report:   {path}')
"
    echo ""
done

echo "=== Demo complete. Reports in reports/ directory. ==="
ls -la reports/*.md 2>/dev/null || echo "(no reports generated — check for errors above)"
