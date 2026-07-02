#!/usr/bin/env python3
"""Local demo runner — executes the full triage pipeline using a local LLM.

Uses the llama.cpp server (gemma4 model) instead of Gemini, so it works
without GOOGLE_API_KEY. Generates real triage reports for all 5 sample PRDs.

Usage:
    # Start the llama server first:
    llama serve --model ~/Models/gemma4-v2-Q4_K_M.gguf --port 8081 --ctx-size 4096

    # Then run this script:
    uv run python scripts/local_demo.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

from agents.completeness import COMPLETENESS_INSTRUCTION  # noqa: E402
from agents.clarity import CLARITY_INSTRUCTION  # noqa: E402
from agents.risk import RISK_INSTRUCTION  # noqa: E402
from agents.orchestrator import apply_critical_risk_veto  # noqa: E402
from doc_mcp.repository import get_prd  # noqa: E402
from models.schemas import (  # noqa: E402
    AuditEntry,
    ClarityReport,
    CompletenessReport,
    PolicyDecision,
    RiskReport,
    TriageReport,
    Verdict,
)
from policy.checker import check_policy  # noqa: E402
from report import write_report  # noqa: E402

LLAMA_URL = "http://localhost:8081/v1/chat/completions"
TIMEOUT = 120

JSON_SUFFIX = """

CRITICAL: Output ONLY a valid JSON object matching the schema above. No markdown, no explanation, no code fences. Start with { and end with }."""


def call_llm(system_prompt: str, user_content: str) -> str:
    resp = requests.post(
        LLAMA_URL,
        json={
            "messages": [
                {"role": "system", "content": system_prompt + JSON_SUFFIX},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_json(text: str) -> dict | None:
    # Strip code fences if present
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    raw = match.group(1).strip() if match else text.strip()
    # Find first { and last }
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None


def normalize_severity(val: str) -> str:
    """Map LLM-generated severity strings to valid enum values."""
    val = str(val).lower().strip()
    valid = {"low", "medium", "high", "critical"}
    if val in valid:
        return val
    if "critical" in val:
        return "critical"
    if "high" in val:
        return "high"
    if "medium" in val:
        return "medium"
    return "low"


def safe_parse(text: str, schema_class):
    data = parse_json(text)
    if data is None:
        print(f"    ⚠️  JSON parse failed, using default")
        return None
    # Normalize severity fields before validation
    if isinstance(data, dict):
        for key in ("severity",):
            if key in data and isinstance(data[key], str):
                data[key] = normalize_severity(data[key])
        for finding in data.get("findings", []):
            if isinstance(finding, dict) and "severity" in finding:
                finding["severity"] = normalize_severity(finding["severity"])
        for section in data.get("missing_sections", []):
            if isinstance(section, dict) and "severity" in section:
                section["severity"] = normalize_severity(section["severity"])
    try:
        return schema_class.model_validate(data)
    except Exception as e:
        print(f"    ⚠️  Schema validation failed: {e}")
        return None


def run_triage(prd_id: str) -> TriageReport:
    print(f"\n{'='*60}")
    print(f"Triaging {prd_id}")
    print(f"{'='*60}")

    # 1. Intake
    prd = get_prd(prd_id)
    if "error" in prd:
        print(f"  ❌ Intake failed: {prd['error']}")
        return TriageReport(
            prd_id=prd_id, verdict=Verdict.REJECT, status="terminated",
            audit_trail=[AuditEntry(stage="intake", status="failed", error=prd["error"])],
        )
    print(f"  ✅ Intake: {prd['title']}")

    # 2. Policy gate
    decision = check_policy(prd["content"])
    if not decision.allowed:
        types = [v.type for v in decision.violations]
        print(f"  🚫 Policy REJECT: {types}")
        return TriageReport(
            prd_id=prd_id, verdict=Verdict.REJECT, status="terminated",
            policy_decision=decision,
            audit_trail=[
                AuditEntry(stage="intake", status="completed"),
                AuditEntry(stage="policy", status="completed", error=f"Rejected: {types}"),
            ],
        )
    print(f"  ✅ Policy: passed")

    content = prd["content"]
    audit = [
        AuditEntry(stage="intake", status="completed"),
        AuditEntry(stage="policy", status="completed"),
    ]

    # 3. Specialist agents (sequential on local model)
    print(f"  🔄 Completeness Checker...")
    t0 = time.time()
    comp_text = call_llm(COMPLETENESS_INSTRUCTION, f"Analyze this PRD:\n\n{content}")
    completeness = safe_parse(comp_text, CompletenessReport)
    print(f"     Done ({time.time()-t0:.1f}s) — score={completeness.completeness_score if completeness else '?'}")

    print(f"  🔄 Clarity Checker...")
    t0 = time.time()
    clarity_text = call_llm(CLARITY_INSTRUCTION, f"Analyze this PRD:\n\n{content}")
    clarity = safe_parse(clarity_text, ClarityReport)
    n_items = len(clarity.ambiguous_items) if clarity else 0
    print(f"     Done ({time.time()-t0:.1f}s) — {n_items} ambiguous items")

    print(f"  🔄 Risk Checker...")
    t0 = time.time()
    risk_text = call_llm(RISK_INSTRUCTION, f"Analyze this PRD:\n\n{content}")
    risk = safe_parse(risk_text, RiskReport)
    n_findings = len(risk.findings) if risk else 0
    print(f"     Done ({time.time()-t0:.1f}s) — {n_findings} findings")

    audit.append(AuditEntry(stage="specialists", status="completed", agent_name="completeness_checker"))
    audit.append(AuditEntry(stage="specialists", status="completed", agent_name="clarity_checker"))
    audit.append(AuditEntry(stage="specialists", status="completed", agent_name="risk_checker"))

    # 4. Synthesis (deterministic — no LLM needed for MVP)
    comp_score = completeness.completeness_score if completeness else 50
    n_clarify = len(clarity.ambiguous_items) if clarity else 0
    has_critical = risk and any(f.severity.value == "critical" for f in risk.findings)

    if has_critical:
        verdict = Verdict.NEEDS_CLARIFICATION
    elif comp_score >= 80 and n_clarify < 3:
        verdict = Verdict.PASS
    else:
        verdict = Verdict.NEEDS_CLARIFICATION

    from models.schemas import ClarifyingQuestion
    clarifying = []
    if clarity:
        for i, item in enumerate(clarity.ambiguous_items[:5]):
            clarifying.append(ClarifyingQuestion(
                question_id=f"q{i+1}",
                question=item.generated_question,
            ))

    report = TriageReport(
        prd_id=prd_id,
        verdict=verdict,
        status="completed",
        completeness=completeness,
        clarity=clarity,
        risk=risk,
        clarifying_questions=clarifying,
        policy_decision=decision,
        audit_trail=audit + [AuditEntry(stage="synthesis", status="completed")],
    )

    # 5. Apply critical-risk veto
    report = apply_critical_risk_veto(report)

    print(f"  📋 Verdict: {report.verdict.value}")
    return report


def main():
    print("PRD Triage Agent — Local Demo (gemma4 via llama.cpp)")
    print(f"LLM endpoint: {LLAMA_URL}")

    # Verify llama server is up
    try:
        requests.get("http://localhost:8081/health", timeout=5)
    except Exception:
        print("❌ llama server not running on port 8081")
        print("Start with: llama serve --model ~/Models/gemma4-v2-Q4_K_M.gguf --port 8081")
        sys.exit(1)

    prd_ids = ["prd-001", "prd-002", "prd-003", "prd-004", "prd-005"]
    results = {}

    for prd_id in prd_ids:
        report = run_triage(prd_id)
        results[prd_id] = report
        path = write_report(report)
        print(f"  📄 Report: {path}")

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for prd_id, report in results.items():
        comp = report.completeness.completeness_score if report.completeness else "—"
        print(f"  {prd_id}: verdict={report.verdict.value:25s} completeness={comp}")

    print(f"\nReports saved to: {Path('reports').resolve()}/")


if __name__ == "__main__":
    main()
