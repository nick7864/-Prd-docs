"""Tests for the Policy gate regex layer.

Per spec D5 verification:
    - `pytest tests/test_policy.py::test_rejects_api_key` passes
    - `pytest tests/test_policy.py::test_rejects_email` passes
    - YAML rules file is human-readable and reviewable
"""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from policy.checker import POLICIES_PATH, check_policy, load_policies  # noqa: E402
from models.schemas import PolicyDecision  # noqa: E402

# NOTE: All API keys in test cases below (AIzaSyDabc123...) are FAKE test fixtures
# for verifying the policy gate's regex detection. NOT real credentials.


# ---------------------------------------------------------------------------
# Rules file sanity
# ---------------------------------------------------------------------------


def test_policies_file_exists_and_is_reviewable():
    """YAML must exist and have at least the google_api_key + email rules."""
    assert POLICIES_PATH.exists(), f"policies.yaml missing at {POLICIES_PATH}"
    data = load_policies()
    rule_ids = {r["id"] for r in data["rules"]}
    assert "google_api_key" in rule_ids
    assert "email" in rule_ids
    # Every rule must declare id + pattern + severity
    for rule in data["rules"]:
        assert "id" in rule
        assert "pattern" in rule
        assert "severity" in rule


# ---------------------------------------------------------------------------
# Per-rule rejection
# ---------------------------------------------------------------------------


def test_rejects_google_api_key():
    """The exact pattern from prd-003 must be rejected."""
    content = "API key for maps: AIzaSyDabc123def456ghi789jkl012mno345pqr"
    decision = check_policy(content)
    assert isinstance(decision, PolicyDecision)
    assert decision.allowed is False
    types = {v.type for v in decision.violations}
    assert "google_api_key" in types
    # Reported pattern is the matched substring
    api_key_v = next(v for v in decision.violations if v.type == "google_api_key")
    assert api_key_v.pattern.startswith("AIza")


def test_rejects_email():
    """A typical email must be rejected with type='email'."""
    content = "Contact john@example.com for details."
    decision = check_policy(content)
    assert decision.allowed is False
    types = {v.type for v in decision.violations}
    assert "email" in types
    email_v = next(v for v in decision.violations if v.type == "email")
    assert "@" in email_v.pattern


def test_rejects_phone_intl():
    content = "Call me at +1-555-123-4567 anytime"
    decision = check_policy(content)
    assert decision.allowed is False
    types = {v.type for v in decision.violations}
    assert "phone_intl" in types


def test_rejects_aws_key():
    content = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
    decision = check_policy(content)
    assert decision.allowed is False
    assert "aws_access_key_id" in {v.type for v in decision.violations}


def test_rejects_github_token():
    content = "GITHUB_TOKEN=ghp_" + "a" * 36
    decision = check_policy(content)
    assert decision.allowed is False
    assert "github_token" in {v.type for v in decision.violations}


def test_rejects_stripe_live_key():
    content = "stripe_key = sk_live_" + "a" * 30
    decision = check_policy(content)
    assert decision.allowed is False
    assert "stripe_live_key" in {v.type for v in decision.violations}


def test_policy_violation_pattern_is_redacted():
    """Secret/PII matched substrings are redacted before leaving check_policy."""
    content = (
        "key: AIzaSyDabc123def456ghi789jkl012mno345pqr\n"
        "email: john@example.com\n"
    )
    decision = check_policy(content)

    api_key_v = next(v for v in decision.violations if v.type == "google_api_key")
    assert "AIzaSyDabc123def456ghi789jkl012mno345pqr" not in api_key_v.pattern
    assert api_key_v.pattern.startswith("AIza")
    assert "…" in api_key_v.pattern
    assert len(api_key_v.pattern) <= 9

    email_v = next(v for v in decision.violations if v.type == "email")
    assert "john@example.com" not in email_v.pattern
    assert "@" in email_v.pattern
    assert "@example.com" in email_v.pattern


# ---------------------------------------------------------------------------
# Clean content
# ---------------------------------------------------------------------------


def test_accepts_clean_prd():
    """Spec example: OAuth 2.0 mention must NOT trigger any rule."""
    content = "The system supports OAuth 2.0 authentication."
    decision = check_policy(content)
    assert decision.allowed is True
    assert decision.violations == []


def test_accepts_prd_001_dark_mode():
    """The complete sample PRD (prd-001) is clean by construction."""
    from doc_mcp.repository import get_prd

    prd = get_prd("prd-001")
    assert "error" not in prd
    decision = check_policy(prd["content"])
    assert decision.allowed is True, (
        f"prd-001 unexpectedly rejected: {[v.type for v in decision.violations]}"
    )


# ---------------------------------------------------------------------------
# Reporting fields
# ---------------------------------------------------------------------------


def test_line_number_reported_correctly():
    """1-based line number points at the offending line."""
    content = "line 1 clean\nline 2 clean\nkey: AIzaSyDabc123def456ghi789jkl012mno345pqr\nline 4"
    decision = check_policy(content)
    api_key_v = next(v for v in decision.violations if v.type == "google_api_key")
    assert api_key_v.line_number == 3


def test_multiple_violations_collected():
    """Two distinct secrets in one doc yield two violations."""
    content = (
        "email: admin@shopflow.example\n"
        "key: AIzaSyDabc123def456ghi789jkl012mno345pqr\n"
    )
    decision = check_policy(content)
    assert decision.allowed is False
    types = {v.type for v in decision.violations}
    assert "email" in types
    assert "google_api_key" in types


def test_multiple_hits_same_rule():
    """Two emails on different lines each get their own violation."""
    content = "a@x.com\nb@y.com"
    decision = check_policy(content)
    email_vs = [v for v in decision.violations if v.type == "email"]
    assert len(email_vs) == 2
    assert {v.line_number for v in email_vs} == {1, 2}


# ---------------------------------------------------------------------------
# Scanner failure mode (deny by default)
# ---------------------------------------------------------------------------


def test_scanner_error_denies(tmp_path):
    """Missing or malformed policies file → deny with scanner_error."""
    bogus = tmp_path / "missing.yaml"
    decision = check_policy("clean content", policies_path=bogus)
    assert decision.allowed is False
    assert any(v.type == "scanner_error" for v in decision.violations)


def test_empty_content_allowed():
    """Empty string is trivially clean."""
    decision = check_policy("")
    assert decision.allowed is True
