"""In-memory registry of paused HITL triage sessions.

Single-process, thread-safe (threading.Lock), TTL-aware via the ``expires_at``
field on each SessionState. Suitable for the demo deployment (one uvicorn
worker, in-process sessions). Not durable across restarts or multiple workers
— see openspec/changes/add-web-frontend/design.md Decision 2.

Callers (the orchestrator) stamp ``created_at``/``expires_at`` when building a
SessionState, using ``default_ttl_seconds()`` so the TTL source is centralized
here. The registry treats any session whose ``expires_at`` is in the past as
nonexistent (``get`` returns None, ``delete`` returns False); ``cleanup_expired``
reclaims the memory.
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone

from models.schemas import SessionState


def default_ttl_seconds() -> int:
    """Read TRIAGE_SESSION_TTL (seconds) from env, defaulting to 3600.

    A missing or non-parseable value falls back to 3600. A non-positive value
    also falls back to 3600 (a TTL of zero would expire sessions instantly,
    which is never the intent).
    """
    raw = os.environ.get("TRIAGE_SESSION_TTL")
    if raw is None:
        return 3600
    try:
        value = int(raw)
    except ValueError:
        return 3600
    return value if value > 0 else 3600


def _is_expired(state: SessionState, now: datetime) -> bool:
    exp = state.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp <= now


class SessionRegistry:
    """Thread-safe map of session_id -> SessionState with TTL semantics."""

    def __init__(self) -> None:
        self._store: dict[str, SessionState] = {}
        self._lock = threading.Lock()

    def create(self, state: SessionState) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._store[session_id] = state
        return session_id

    def get(self, session_id: str) -> SessionState | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            state = self._store.get(session_id)
            if state is None:
                return None
            if _is_expired(state, now):
                return None
            return state

    def delete(self, session_id: str) -> bool:
        now = datetime.now(timezone.utc)
        with self._lock:
            state = self._store.pop(session_id, None)
            if state is None:
                return False
            # An already-expired session is treated as nonexistent.
            return not _is_expired(state, now)

    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            doomed = [sid for sid, st in self._store.items() if _is_expired(st, now)]
            for sid in doomed:
                self._store.pop(sid, None)
        return len(doomed)
