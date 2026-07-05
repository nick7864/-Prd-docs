"""Tests for the synthesis agent restructure (fix-synthesis-state).

Covers:
- _prepare_synthesis_inputs callback (JSON-serializes specialist state, labels
  absent optional specialists "MISSING").
- synthesis_agent config (small output schema, output_key, callback wired).
"""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents.synthesis import _prepare_synthesis_inputs, synthesis_agent  # noqa: E402
from models.schemas import SynthesisOutput  # noqa: E402


class _FakeCallbackContext:
    def __init__(self, state):
        self.state = state


def test_prepare_synthesis_inputs_json_serializes_state():
    ctx = _FakeCallbackContext({
        "completeness_report": {"completeness_score": 40, "missing_sections": []},
        "clarity_report": {"ambiguous_items": []},
        "architecture_report": {"conflicts": []},
        "risk_report": {"findings": []},
    })
    _prepare_synthesis_inputs(ctx)
    for key in ("completeness_report", "clarity_report",
                "architecture_report", "risk_report"):
        value = ctx.state[key]
        assert isinstance(value, str)
        assert value.startswith("{")


def test_prepare_synthesis_inputs_labels_absent_optional_as_missing():
    ctx = _FakeCallbackContext({
        "completeness_report": {"completeness_score": 80},
        "clarity_report": {"ambiguous_items": []},
        "architecture_report": None,
        "risk_report": None,
    })
    _prepare_synthesis_inputs(ctx)
    assert ctx.state["architecture_report"] == "MISSING"
    assert ctx.state["risk_report"] == "MISSING"


def test_prepare_synthesis_inputs_preserves_string_values():
    ctx = _FakeCallbackContext({
        "completeness_report": '{"already": "json"}',
        "clarity_report": None,
        "architecture_report": None,
        "risk_report": None,
    })
    _prepare_synthesis_inputs(ctx)
    assert ctx.state["completeness_report"] == '{"already": "json"}'


def test_prepare_synthesis_inputs_returns_none():
    ctx = _FakeCallbackContext({})
    assert _prepare_synthesis_inputs(ctx) is None


def test_synthesis_agent_uses_small_schema_and_output_key():
    assert synthesis_agent.output_schema is SynthesisOutput
    assert synthesis_agent.output_key == "synthesis_output"


def test_synthesis_agent_has_prepare_callback():
    assert synthesis_agent.before_agent_callback is _prepare_synthesis_inputs


def test_synthesis_instruction_references_specialist_placeholders():
    instr = synthesis_agent.instruction
    assert "{completeness_report}" in instr
    assert "{clarity_report}" in instr
    assert "{architecture_report?}" in instr
    assert "{risk_report?}" in instr
