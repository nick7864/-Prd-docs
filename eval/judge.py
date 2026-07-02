#!/usr/bin/env python3
"""LLM-as-judge evaluation script for the PRD Triage Agent.

Usage:
    export GOOGLE_API_KEY="..."
    python eval/judge.py

Loads eval/evalset.jsonl, runs each test case through the triage pipeline,
and checks results against expected assertions. Works partially without
GOOGLE_API_KEY (policy/intake paths); full evaluation requires the key
for LLM-based completeness and clarity checks.

Exit code: 0 if all checks pass, 1 otherwise.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.orchestrator import triage  # noqa: E402


def load_evalset() -> list[dict]:
    evalset_path = Path(__file__).parent / "evalset.jsonl"
    cases = []
    for line in evalset_path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            cases.append(json.loads(line))
    return cases


def evaluate_case(case: dict) -> dict:
    prd_id = case["prd_id"]
    expected_verdict = case.get("expected_verdict")
    report = triage(prd_id)

    result: dict = {
        "prd_id": prd_id,
        "expected_verdict": expected_verdict,
        "actual_verdict": report.verdict.value,
        "verdict_correct": report.verdict.value == expected_verdict,
        "checks": [],
    }

    if "expected_policy_violation" in case:
        expected_type = case["expected_policy_violation"]
        if report.policy_decision:
            types = {v.type for v in report.policy_decision.violations}
            passed = expected_type in types
        else:
            passed = False
        result["checks"].append({
            "name": f"policy_violation:{expected_type}",
            "passed": passed,
        })

    if "expected_completeness_min" in case:
        threshold = case["expected_completeness_min"]
        actual = report.completeness.completeness_score if report.completeness else 0
        result["checks"].append({
            "name": f"completeness >= {threshold}",
            "passed": actual >= threshold,
            "actual": actual,
        })

    if "expected_completeness_max" in case:
        threshold = case["expected_completeness_max"]
        actual = report.completeness.completeness_score if report.completeness else 0
        result["checks"].append({
            "name": f"completeness <= {threshold}",
            "passed": actual <= threshold,
            "actual": actual,
        })

    if "expected_missing_section" in case and report.completeness:
        expected_section = case["expected_missing_section"]
        missing = [s.section for s in report.completeness.missing_sections]
        result["checks"].append({
            "name": f"missing_section:{expected_section}",
            "passed": expected_section in missing,
        })

    if "expected_vague_terms" in case and report.clarity:
        for term in case["expected_vague_terms"]:
            found = any(
                term in item.phrase.lower()
                for item in report.clarity.ambiguous_items
            )
            result["checks"].append({
                "name": f"vague_term:{term}",
                "passed": found,
            })

    return result


def run_evaluation() -> list[dict]:
    cases = load_evalset()
    print("=" * 60)
    print("PRD Triage Agent — Evaluation Suite")
    print("=" * 60)
    print(f"Test cases: {len(cases)}\n")

    all_results = []
    total = 0
    passed = 0

    for case in cases:
        print(f"--- {case['prd_id']} ---")
        result = evaluate_case(case)
        all_results.append(result)

        icon = "\u2705" if result["verdict_correct"] else "\u274c"
        print(f"  Verdict: {icon} expected={result['expected_verdict']}, "
              f"actual={result['actual_verdict']}")

        for check in result["checks"]:
            ci = "\u2705" if check["passed"] else "\u274c"
            extra = f" (actual: {check['actual']})" if "actual" in check else ""
            print(f"  {ci} {check['name']}{extra}")
            total += 1
            if check["passed"]:
                passed += 1

        if case.get("notes"):
            print(f"  Notes: {case['notes']}")
        print()

    print("=" * 60)
    print(f"Checks: {passed}/{total} passed")
    verdict_acc = sum(1 for r in all_results if r["verdict_correct"]) / len(all_results)
    print(f"Verdict accuracy: {verdict_acc:.0%}")
    print("=" * 60)

    return all_results


if __name__ == "__main__":
    if not os.environ.get("GOOGLE_API_KEY"):
        print("WARNING: GOOGLE_API_KEY not set.")
        print("Only policy/intake paths will produce correct results.")
        print("Set with: export GOOGLE_API_KEY='your-key'\n")

    results = run_evaluation()
    all_passed = all(
        check["passed"]
        for result in results
        for check in result["checks"]
    )
    sys.exit(0 if all_passed else 1)
