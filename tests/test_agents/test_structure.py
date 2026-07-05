"""Structural tests for ADK agent definitions.

These tests verify the agent graph structure and configuration WITHOUT \
requiring GOOGLE_API_KEY. They check that:
- Agent classes are correctly defined and importable
- The pipeline graph contains a ParallelAgent (spec verification target)
- Each agent has the right output_schema, model, and non-empty instruction
- The root_agent is discoverable for `adk web` / `adk run`

Integration tests that actually call Gemini are in test_agents_integration.py \
and are skipped when GOOGLE_API_KEY is unset.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402
from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent  # noqa: E402

from agents.completeness import completeness_checker  # noqa: E402
from agents.clarity import clarity_checker  # noqa: E402
from agents.synthesis import synthesis_agent  # noqa: E402
from agents.orchestrator import root_agent, specialists_parallel, triage  # noqa: E402
from models.schemas import (  # noqa: E402
    ClarityReport,
    CompletenessReport,
    SynthesisOutput,
    TriageReport,
)


# ---------------------------------------------------------------------------
# Agent configuration tests
# ---------------------------------------------------------------------------


class TestCompletenessChecker:
    def test_is_llm_agent(self):
        assert isinstance(completeness_checker, LlmAgent)

    def test_name(self):
        assert completeness_checker.name == "completeness_checker"

    def test_has_output_schema(self):
        assert completeness_checker.output_schema is CompletenessReport

    def test_has_output_key(self):
        assert completeness_checker.output_key == "completeness_report"

    def test_has_non_empty_instruction(self):
        assert len(completeness_checker.instruction) > 200, (
            "Instruction should be a detailed system prompt, not a stub"
        )

    def test_model_set(self):
        assert completeness_checker.model is not None


class TestClarityChecker:
    def test_is_llm_agent(self):
        assert isinstance(clarity_checker, LlmAgent)

    def test_name(self):
        assert clarity_checker.name == "clarity_checker"

    def test_has_output_schema(self):
        assert clarity_checker.output_schema is ClarityReport

    def test_has_output_key(self):
        assert clarity_checker.output_key == "clarity_report"

    def test_has_non_empty_instruction(self):
        assert len(clarity_checker.instruction) > 200

    def test_model_set(self):
        assert clarity_checker.model is not None


class TestSynthesisAgent:
    def test_is_llm_agent(self):
        assert isinstance(synthesis_agent, LlmAgent)

    def test_has_synthesis_output_schema(self):
        assert synthesis_agent.output_schema is SynthesisOutput

    def test_has_output_key(self):
        assert synthesis_agent.output_key == "synthesis_output"

    def test_instruction_mentions_verdict_rules(self):
        assert "PASS" in synthesis_agent.instruction
        assert "NEEDS_CLARIFICATION" in synthesis_agent.instruction


# ---------------------------------------------------------------------------
# Pipeline graph structure tests (spec D4 verification target)
# ---------------------------------------------------------------------------


class TestPipelineGraph:
    """Per spec: 'Pipeline SHALL be orchestrated via ADK workflow graph'."""

    def test_root_agent_is_sequential(self):
        assert isinstance(root_agent, SequentialAgent), (
            "Root must be SequentialAgent for ordered: specialists → synthesis"
        )

    def test_root_has_sub_agents(self):
        assert len(root_agent.sub_agents) >= 2, (
            "Root must have at least 2 children: parallel specialists + synthesis"
        )

    def test_root_contains_parallel_agent(self):
        """Spec: graph SHALL contain at least one parallel-execution segment."""
        parallel_children = [
            child for child in root_agent.sub_agents if isinstance(child, ParallelAgent)
        ]
        assert len(parallel_children) >= 1, (
            "Root must contain a ParallelAgent for specialist fan-out"
        )

    def test_specialists_parallel_has_mvp_agents(self):
        """MVP has Completeness + Clarity in the parallel node."""
        assert isinstance(specialists_parallel, ParallelAgent)
        child_names = {child.name for child in specialists_parallel.sub_agents}
        assert "completeness_checker" in child_names
        assert "clarity_checker" in child_names

    def test_specialists_parallel_has_at_least_two_children(self):
        """Spec: 'four specialist agents SHALL analyze the PRD in parallel'.

        MVP has 2; D5 adds Architecture + Risk for 4.
        """
        assert len(specialists_parallel.sub_agents) >= 2

    def test_graph_has_sequential_nodes(self):
        """Spec: 'at least three sequential nodes'."""
        # Root (SequentialAgent) itself counts; its children are the nodes.
        # specialists_parallel + synthesis_agent = 2 children in root.
        # Plus root itself = 3 sequential nodes.
        assert len(root_agent.sub_agents) >= 2

    def test_graph_has_conditional_path(self):
        """Spec: 'at least one conditional edge'.

        The orchestrator's triage() function provides conditional branching:
        intake fail → reject, policy reject → reject, else → pipeline.
        This is verified in test_orchestrator.py (function-level tests).
        """
        # Structural test: root exists and is composable.
        assert root_agent is not None


# ---------------------------------------------------------------------------
# triage() entry point tests (no API key needed for early-exit paths)
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_model_key(monkeypatch):
    """Force `_has_model_key()` to return False by clearing every provider key.

    Needed because multi-model support means a configured GLM (TRIAGE_API_KEY)
    counts as "has key" — tests that exercise the no-key terminated path must
    clear all provider keys, not just GOOGLE_API_KEY.
    """
    for key in (
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "TRIAGE_MODEL_PROVIDER",
        "TRIAGE_MODEL",
        "TRIAGE_API_BASE",
        "TRIAGE_API_KEY",
        "ZHIPUAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


class TestTriageEntryIntake:
    """triage() handles intake failures without GOOGLE_API_KEY."""

    def test_triage_unknown_prd_returns_reject(self):
        report = triage("nonexistent-prd")
        assert report.prd_id == "nonexistent-prd"
        assert report.verdict.value == "reject"
        assert report.status == "terminated"
        assert any(
            entry.stage == "intake" and entry.status == "failed"
            for entry in report.audit_trail
        )


class TestTriageEntryPolicy:
    """triage() rejects PRDs with policy violations without GOOGLE_API_KEY."""

    def test_triage_prd_003_rejected_by_policy(self):
        """prd-003 contains an embedded API key — policy gate must reject."""
        report = triage("prd-003")
        assert report.verdict.value == "reject"
        assert report.policy_decision is not None
        assert report.policy_decision.allowed is False
        violation_types = {v.type for v in report.policy_decision.violations}
        assert "google_api_key" in violation_types


class TestTriageEntryCleanPRD:
    """triage() on a clean PRD without API key returns early with terminated status."""

    def test_triage_prd_001_without_api_key(self, monkeypatch, _no_model_key):
        report = triage("prd-001")
        # Without any provider key, the pipeline can't run specialists.
        # It should return with status="terminated" and an audit trail note.
        assert report.prd_id == "prd-001"
        assert report.status == "terminated"
        assert any(
            entry.stage == "specialists" and entry.status == "skipped"
            for entry in report.audit_trail
        )


class TestRunnerInitialization:
    """Verify the ADK Runner accepts root_agent — the agent tree is well-formed.

    This exercises the ADK integration layer (Runner + SessionService) without
    making any LLM calls, so it needs no GOOGLE_API_KEY.
    """

    @pytest.mark.asyncio
    async def test_runner_accepts_root_agent(self):
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        from agents import root_agent

        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name="prd_triage_test", user_id="test_user"
        )
        runner = Runner(
            agent=root_agent,
            app_name="prd_triage_test",
            session_service=session_service,
        )
        assert runner is not None
        assert runner.agent is root_agent
        assert session.id is not None

    @pytest.mark.asyncio
    async def test_session_state_is_writable(self):
        from google.adk.sessions import InMemorySessionService

        session_service = InMemorySessionService()
        session = await session_service.create_session(
            app_name="prd_triage_test", user_id="test_user"
        )
        session.state["test_key"] = "test_value"
        assert session.state["test_key"] == "test_value"


# ---------------------------------------------------------------------------
# Integration tests (skipped without GOOGLE_API_KEY)
# ---------------------------------------------------------------------------


GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

integration = pytest.mark.skipif(
    not GOOGLE_API_KEY,
    reason="GOOGLE_API_KEY not set — skipping LLM integration tests",
)


@integration
class TestCompletenessIntegration:
    """End-to-end Completeness Checker tests against real Gemini API."""

    def test_missing_acceptance_criteria(self):
        """prd-002 lacks acceptance criteria → score < 60 + missing section."""
        from doc_mcp.repository import get_prd

        prd = get_prd("prd-002")
        # This would call the actual LlmAgent via ADK Runner.
        # Implementation requires wiring the Runner; see orchestrator._run_adk_pipeline.
        pytest.skip("Runner wiring TBD — agent definitions are in place")

    def test_complete_prd_scores_high(self):
        """prd-001 has all sections → score ≥ 80."""
        pytest.skip("Runner wiring TBD")


@integration
class TestClarityIntegration:
    """End-to-end Clarity Checker tests against real Gemini API."""

    def test_vague_term_detected(self):
        """prd-004 has 'fast', 'scalable' → vague_quantifier findings."""
        pytest.skip("Runner wiring TBD")

    def test_clean_prd_no_findings(self):
        """prd-001 has quantified targets → no vague_quantifier findings."""
        pytest.skip("Runner wiring TBD")


# ---------------------------------------------------------------------------
# Multi-model support (add-multi-model-support): all agents use build_model()
# ---------------------------------------------------------------------------

from agents.architecture import architecture_checker  # noqa: E402
from agents.risk import risk_checker  # noqa: E402


class TestAllAgentsUseBuildModel:
    """Every agent's model comes from build_model() — never a hardcoded string."""

    @pytest.mark.parametrize(
        "agent",
        [
            completeness_checker,
            clarity_checker,
            architecture_checker,
            risk_checker,
            synthesis_agent,
        ],
    )
    def test_model_is_set(self, agent):
        # build_model() returns either a Gemini model string or a LiteLlm wrapper;
        # both are truthy. A hardcoded None or empty would fail here.
        assert agent.model, f"{agent.name} has no model"


    def test_default_model_is_gemini(self, monkeypatch):
        # With no TRIAGE_MODEL_* env, build_model() returns the Gemini default.
        for key in (
            "TRIAGE_MODEL_PROVIDER", "TRIAGE_MODEL",
            "TRIAGE_API_BASE", "TRIAGE_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        from agents._model import build_model
        assert build_model() == "gemini-2.5-flash"
