"""Tests for the architecture agent restructure (add-multi-model-support).

Covers the before_agent_callback that replaces the previous ADK tool, so the
architecture agent no longer depends on the Gemini-only tools+output_schema
combination.
"""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from agents.architecture import (  # noqa: E402
    _prepare_architecture_context,
    architecture_checker,
)


class _FakeCallbackContext:
    def __init__(self):
        self.state = {}


def test_prepare_architecture_context_injects_json(monkeypatch):
    monkeypatch.setattr(
        "agents.architecture.get_architecture_context",
        lambda: {"architecture_doc": "...", "adrs": [{"id": "ADR-001"}]},
    )
    ctx = _FakeCallbackContext()
    assert _prepare_architecture_context(ctx) is None
    value = ctx.state["architecture_context"]
    assert isinstance(value, str)
    assert value.startswith("{")


def test_prepare_architecture_context_missing_on_failure(monkeypatch):
    def boom():
        raise RuntimeError("disk gone")

    monkeypatch.setattr("agents.architecture.get_architecture_context", boom)
    ctx = _FakeCallbackContext()
    _prepare_architecture_context(ctx)
    assert ctx.state["architecture_context"] == "MISSING"


def test_prepare_architecture_context_missing_on_error_dict(monkeypatch):
    monkeypatch.setattr(
        "agents.architecture.get_architecture_context",
        lambda: {"error": "not found"},
    )
    ctx = _FakeCallbackContext()
    _prepare_architecture_context(ctx)
    assert ctx.state["architecture_context"] == "MISSING"


def test_architecture_checker_has_no_tools():
    assert not getattr(architecture_checker, "tools", None)


def test_architecture_checker_has_prepare_callback():
    assert architecture_checker.before_agent_callback is _prepare_architecture_context


def test_architecture_instruction_reads_context_placeholder():
    assert "{architecture_context}" in architecture_checker.instruction


def test_architecture_instruction_does_not_mention_tool_call():
    instr = architecture_checker.instruction
    assert "Call the `get_architecture_context` tool" not in instr
