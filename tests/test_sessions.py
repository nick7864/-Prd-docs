"""Tests for the in-memory HITL SessionRegistry."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from models.schemas import (  # noqa: E402
    PolicyDecision,
    SessionState,
    TriageReport,
    Verdict,
)
from sessions.registry import SessionRegistry, default_ttl_seconds  # noqa: E402


def _state(
    prd_id: str = "prd-002",
    *,
    expires_at: datetime | None = None,
) -> SessionState:
    now = datetime.now(timezone.utc)
    return SessionState(
        prd_id=prd_id,
        prd_content="some content",
        policy_decision=PolicyDecision(allowed=True),
        partial_report=TriageReport(prd_id=prd_id, verdict=Verdict.NEEDS_CLARIFICATION),
        created_at=now,
        expires_at=expires_at or now + timedelta(hours=1),
    )


# ---------------------------------------------------------------------------
# 1.2 create / get / delete
# ---------------------------------------------------------------------------


def test_create_get_round_trip():
    reg = SessionRegistry()
    sid = reg.create(_state())
    got = reg.get(sid)
    assert got is not None
    assert got.prd_id == "prd-002"
    assert got.partial_report.verdict is Verdict.NEEDS_CLARIFICATION


def test_get_unknown_returns_none():
    reg = SessionRegistry()
    assert reg.get("nonexistent") is None


def test_delete_removes_session():
    reg = SessionRegistry()
    sid = reg.create(_state())
    assert reg.delete(sid) is True
    assert reg.get(sid) is None
    # Second delete: already gone.
    assert reg.delete(sid) is False


def test_concurrent_create_delete_is_safe():
    reg = SessionRegistry()
    errors: list[BaseException] = []

    def worker():
        try:
            for _ in range(200):
                sid = reg.create(_state())
                reg.get(sid)
                reg.delete(sid)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # All workers deleted what they created; store should be drained.
    assert reg.cleanup_expired() == 0


# ---------------------------------------------------------------------------
# 1.3 TTL expiry
# ---------------------------------------------------------------------------


def test_expired_session_is_invisible():
    reg = SessionRegistry()
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    sid = reg.create(_state(expires_at=past))
    assert reg.get(sid) is None


def test_delete_on_expired_returns_false():
    reg = SessionRegistry()
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    sid = reg.create(_state(expires_at=past))
    # Expired sessions are treated as nonexistent.
    assert reg.delete(sid) is False
    # And a subsequent get is still None.
    assert reg.get(sid) is None


def test_cleanup_removes_only_expired():
    reg = SessionRegistry()
    now = datetime.now(timezone.utc)
    expired_sid = reg.create(_state(prd_id="expired", expires_at=now - timedelta(seconds=1)))
    valid_sid = reg.create(_state(prd_id="valid", expires_at=now + timedelta(hours=1)))

    removed = reg.cleanup_expired()
    assert removed == 1
    assert reg.get(expired_sid) is None
    assert reg.get(valid_sid) is not None
    assert reg.get(valid_sid).prd_id == "valid"


def test_default_ttl_seconds_defaults(monkeypatch):
    monkeypatch.delenv("TRIAGE_SESSION_TTL", raising=False)
    assert default_ttl_seconds() == 3600


def test_default_ttl_seconds_reads_env(monkeypatch):
    monkeypatch.setenv("TRIAGE_SESSION_TTL", "120")
    assert default_ttl_seconds() == 120


def test_default_ttl_seconds_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("TRIAGE_SESSION_TTL", "not-a-number")
    assert default_ttl_seconds() == 3600


def test_default_ttl_seconds_falls_back_on_nonpositive(monkeypatch):
    monkeypatch.setenv("TRIAGE_SESSION_TTL", "0")
    assert default_ttl_seconds() == 3600
