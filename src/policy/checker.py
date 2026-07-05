"""Policy gate — regex-based scan of PRD content for PII / secret patterns.

Per design.md Decision: Policy gate via regex patterns + lightweight LLM
triage. This module is the deterministic regex layer (must-have); the optional
LLM semantic layer for descriptive PII (e.g. "customer list") is a separate
strengthening step not yet implemented.

Public API:
    check_policy(prd_content: str) -> PolicyDecision
    load_policies() -> dict

Failure mode: any regex engine error yields a deny-by-default decision with a
``scanner_error`` violation entry (never silently allow).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from models.schemas import PolicyDecision, PolicyViolation

POLICIES_PATH = Path(__file__).resolve().parent / "policies.yaml"

# Redaction config — (prefix_len, suffix_len) for token-style secret rules.
# The prefix identifies the rule type (AIza, AKIA, ghp_, sk_live_, eyJ, xoxb-);
# the last 4 chars give the reviewer a fingerprint without exposing the middle.
_TOKEN_KEEP: dict[str, tuple[int, int]] = {
    "google_api_key": (4, 4),
    "aws_access_key_id": (4, 4),
    "github_token": (4, 4),
    "slack_token": (5, 4),
    "stripe_live_key": (8, 4),
    "jwt_token": (3, 4),
}

_CC_RE = re.compile(r"^\+\d{1,3}")


def _redact(rule_id: str, matched: str) -> str:
    """Redact a matched substring for safe display.

    Secret tokens keep a type-identifying prefix + last 4 chars (middle → ``…``).
    Emails keep the first 1-2 chars of the local part + the full domain.
    Phones keep ``+CC`` + last 2 digits.
    Benign matches (identifier names like ``aws_secret_key_name``, PEM header
    labels, scanner error messages) and any unknown rule pass through unchanged.
    """
    if rule_id in _TOKEN_KEEP:
        prefix_len, suffix_len = _TOKEN_KEEP[rule_id]
        if len(matched) <= prefix_len + suffix_len:
            return matched[:prefix_len] + "…"
        return f"{matched[:prefix_len]}…{matched[-suffix_len:]}"
    if rule_id == "email":
        if "@" not in matched:
            return matched
        local, _, domain = matched.partition("@")
        head = local[:2] if len(local) >= 2 else local[:1]
        return f"{head}…@{domain}"
    if rule_id == "phone_intl":
        cc = _CC_RE.match(matched)
        cc_part = cc.group() if cc else matched[:2]
        if len(matched) <= len(cc_part) + 2:
            return f"{cc_part}…"
        return f"{cc_part}…{matched[-2:]}"
    return matched


def load_policies(path: Path = POLICIES_PATH) -> dict[str, Any]:
    """Load the policies YAML. Raises if the file is missing or malformed."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"policies file {path} did not yield a mapping")
    return data


def check_policy(
    prd_content: str,
    policies_path: Path = POLICIES_PATH,
) -> PolicyDecision:
    """Scan ``prd_content`` against every rule in the policies file.

    Returns ``PolicyDecision(allowed=False, violations=[...])`` on any hit.
    Returns ``PolicyDecision(allowed=True)`` when content is clean.
    On scanner / loader error: returns deny with a single ``scanner_error``
    violation (safe default — never allow when the scanner itself is broken).
    """
    try:
        policies = load_policies(policies_path)
    except Exception as exc:
        return PolicyDecision(
            allowed=False,
            violations=[
                PolicyViolation(
                    type="scanner_error",
                    pattern=f"policies load failed: {exc!r}",
                    line_number=None,
                )
            ],
        )

    rules = policies.get("rules", []) or []
    violations: list[PolicyViolation] = []
    lines = prd_content.splitlines()

    for rule in rules:
        pattern_str = str(rule.get("pattern", ""))
        rule_id = str(rule.get("id", "unknown"))
        try:
            regex = re.compile(pattern_str)
        except re.error as exc:
            print(
                f"[policy] rule {rule_id!r} has invalid regex {pattern_str!r}: {exc}",
                file=sys.stderr,
            )
            continue

        for line_num, line in enumerate(lines, start=1):
            for match in regex.finditer(line):
                violations.append(
                    PolicyViolation(
                        type=rule_id,
                        pattern=_redact(rule_id, match.group()),
                        line_number=line_num,
                    )
                )

    return PolicyDecision(allowed=not violations, violations=violations)
