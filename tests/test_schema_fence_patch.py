"""Tests for the markdown fence-stripping patch (multi-model GLM compatibility)."""
from __future__ import annotations

from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agents import _schema_fence_patch  # noqa: E402
from models.schemas import CompletenessReport  # noqa: E402


class TestStripFences:
    def test_strips_json_fence(self):
        fenced = '```json\n{"completeness_score": 88}\n```'
        assert _schema_fence_patch._strip_fences(fenced) == '{"completeness_score": 88}'

    def test_strips_bare_fence(self):
        fenced = '```\n{"completeness_score": 88}\n```'
        assert _schema_fence_patch._strip_fences(fenced) == '{"completeness_score": 88}'

    def test_no_op_on_clean_json(self):
        clean = '{"completeness_score": 88}'
        assert _schema_fence_patch._strip_fences(clean) == clean

    def test_no_op_on_non_string(self):
        assert _schema_fence_patch._strip_fences(None) is None
        assert _schema_fence_patch._strip_fences(123) == 123

    def test_handles_surrounding_whitespace(self):
        fenced = '\n\n  ```json\n{"a": 1}\n```  \n'
        assert _schema_fence_patch._strip_fences(fenced) == '{"a": 1}'


class TestPatchedValidateSchemaAcceptsFencedJson:
    """The actual ADK integration point: a fenced JSON that ADK would reject
    now validates through the patched validate_schema."""

    def test_fenced_completeness_report_validates(self):
        fenced = (
            '```json\n'
            '{"completeness_score": 88, "missing_sections": [], "raw_analysis": "ok"}\n'
            '```'
        )
        result = _schema_fence_patch.validate_schema(CompletenessReport, fenced)
        assert result["completeness_score"] == 88

    def test_clean_json_still_validates(self):
        clean = '{"completeness_score": 70, "missing_sections": [], "raw_analysis": ""}'
        result = _schema_fence_patch.validate_schema(CompletenessReport, clean)
        assert result["completeness_score"] == 70


class TestValidateSchemaNonFatal:
    """A malformed model output (invalid JSON even after fence-strip + repair)
    MUST NOT raise — it returns None so the orchestrator degrades gracefully
    instead of crashing the triage. (GLM occasionally emits structurally
    invalid JSON.)"""

    def test_invalid_json_returns_none(self):
        broken = '{"completeness_score": 88, "missing_sections": [...]'  # no closing brace
        assert _schema_fence_patch.validate_schema(CompletenessReport, broken) is None

    def test_wrong_types_return_none(self):
        bad = '{"completeness_score": "not-an-int"}'
        assert _schema_fence_patch.validate_schema(CompletenessReport, bad) is None

    def test_non_json_text_returns_none(self):
        assert _schema_fence_patch.validate_schema(CompletenessReport, "the PRD looks fine") is None


class TestJsonRepairRecovery:
    """The recovery path: extract {...} from prose, repair malformed JSON via
    json-repair, then re-validate. These cases previously returned None and
    would have surfaced as '未執行' in the report."""

    def test_prose_wrapped_json_recovers(self):
        prose = (
            '# CompletenessReport\n'
            'Here is my analysis:\n'
            '{"completeness_score": 88, "missing_sections": [], "raw_analysis": "ok"}\n'
            'Done.'
        )
        result = _schema_fence_patch.validate_schema(CompletenessReport, prose)
        assert result["completeness_score"] == 88

    def test_missing_comma_recovers(self):
        malformed = (
            '{"completeness_score": 88'
            ' "missing_sections": [], "raw_analysis": "ok"}'  # missing comma after 88
        )
        result = _schema_fence_patch.validate_schema(CompletenessReport, malformed)
        assert result["completeness_score"] == 88

    def test_trailing_comma_recovers(self):
        malformed = (
            '{"completeness_score": 88, "missing_sections": [],'
            ' "raw_analysis": "ok",}'  # trailing comma
        )
        result = _schema_fence_patch.validate_schema(CompletenessReport, malformed)
        assert result["completeness_score"] == 88

    def test_pure_prose_no_json_returns_none(self):
        prose = '# RiskReport — PRD-001\nThis PRD looks fine, no risks found.'
        assert _schema_fence_patch.validate_schema(CompletenessReport, prose) is None

    def test_fence_plus_prose_recovers(self):
        mixed = (
            '```json\n'
            'Result:\n'
            '{"completeness_score": 70, "missing_sections": [], "raw_analysis": ""}\n'
            '```\n'
        )
        result = _schema_fence_patch.validate_schema(CompletenessReport, mixed)
        assert result["completeness_score"] == 70


class TestPatchAppliedToAdkModules:
    """The patch must have rewired both the source module and llm_agent's alias."""

    def test_schema_utils_patched(self):
        from google.adk.utils import _schema_utils
        assert _schema_utils.validate_schema is _schema_fence_patch.validate_schema

    def test_llm_agent_alias_patched(self):
        from google.adk.agents import llm_agent
        assert llm_agent.validate_schema is _schema_fence_patch.validate_schema
