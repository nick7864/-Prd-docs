"""Pydantic schemas for structured agent output.

All specialist agents emit one of these report types; the Synthesis Agent
consumes them to build the composite ``TriageReport``. Keeping schemas in one
module lets us version the contract independently of agent implementations.

Field names mirror the spec contracts in
``openspec/changes/add-prd-triager/design.md``.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Standard severity ladder used across all specialist findings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(str, Enum):
    """Final triage verdict emitted by the Synthesis Agent."""

    PASS = "pass"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECT = "reject"


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


class Finding(BaseModel):
    """Shared finding type — the minimal structure every agent finding shares.

    Specialist reports extend this with their own extra fields (e.g. Risk adds
    ``compliance_framework``, Clarity adds ``generated_question``).
    """

    description: str
    severity: Severity


# ---------------------------------------------------------------------------
# Policy gate (D5)
# ---------------------------------------------------------------------------


class PolicyViolation(BaseModel):
    """A single regex-pattern hit from the policy gate."""

    type: str = Field(
        ..., description="Rule id, e.g. 'google_api_key', 'email', 'phone'"
    )
    pattern: str = Field(
        ...,
        description=(
            "The matched substring, redacted for safe display — "
            "secret/PII patterns show prefix…suffix only; benign patterns "
            "(identifier names, PEM labels) pass through unchanged."
        ),
    )
    line_number: Optional[int] = Field(
        None, ge=1, description="1-based line number where the match occurred"
    )


class PolicyDecision(BaseModel):
    """Output of ``check_policy(prd_content)``."""

    allowed: bool
    violations: list[PolicyViolation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Specialist reports (D3 + D5)
# ---------------------------------------------------------------------------


class MissingSection(BaseModel):
    """Entry in CompletenessReport.missing_sections."""

    section: str = Field(
        ...,
        description="Section id like 'acceptance_criteria', 'non_functional_requirements'",
    )
    severity: Severity


class CompletenessReport(BaseModel):
    """Output of the Completeness Checker agent."""

    agent_name: str = "completeness"
    completeness_score: int = Field(..., ge=0, le=100)
    missing_sections: list[MissingSection] = Field(default_factory=list)
    raw_analysis: str = ""


class AmbiguousItem(BaseModel):
    """Entry in ClarityReport.ambiguous_items."""

    phrase: str = Field(..., description="The flagged term, e.g. 'fast'")
    type: str = Field(
        ...,
        description="Category like 'vague_quantifier', 'contradiction', 'undefined_term'",
    )
    generated_question: str = Field(
        ..., description="Clarifying question addressed to the PM"
    )


class ClarityReport(BaseModel):
    """Output of the Clarity Checker agent."""

    agent_name: str = "clarity"
    ambiguous_items: list[AmbiguousItem] = Field(default_factory=list)
    raw_analysis: str = ""


class ArchitectureConflict(BaseModel):
    """Entry in ArchitectureReport.conflicts."""

    description: str
    severity: Severity


class IntegrationPoint(BaseModel):
    """System touch-point the PRD implies."""

    description: str
    service: Optional[str] = Field(
        None, description="Existing service the PRD integrates with"
    )


class ArchitectureReport(BaseModel):
    """Output of the Architecture Fit Assessor agent."""

    agent_name: str = "architecture"
    conflicts: list[ArchitectureConflict] = Field(default_factory=list)
    integration_points: list[IntegrationPoint] = Field(default_factory=list)
    raw_analysis: str = ""


class RiskFinding(Finding):
    """Entry in RiskReport.findings. Extends Finding with compliance context.

    Extends Finding (not separate BaseModel) so risk findings can be stored in
    TriageReport.risk_register (typed list[Finding]) via polymorphism.
    """

    compliance_framework: Optional[str] = Field(
        None, description="e.g. 'GDPR', 'PCI-DSS', 'HIPAA'"
    )


class RiskReport(BaseModel):
    """Output of the Risk and Compliance Checker agent."""

    agent_name: str = "risk"
    findings: list[RiskFinding] = Field(default_factory=list)
    raw_analysis: str = ""


class FailedReport(BaseModel):
    """Report emitted by the orchestrator when a specialist raises an exception.

    Per Decision: ADK Parallel workflow for specialist fan-out — failure of one
    agent does NOT abort the pipeline; the orchestrator catches and emits this.
    """

    agent_name: str
    status: Literal["failed"] = "failed"
    error: str


# ---------------------------------------------------------------------------
# HITL gate (D5)
# ---------------------------------------------------------------------------


class ClarifyingQuestion(BaseModel):
    """A question the pipeline pauses on for PM response."""

    question_id: str
    question: str
    context: Optional[str] = Field(
        None, description="Why this question matters, for PM context"
    )


class PmAnswer(BaseModel):
    """PM's response to a clarifying question."""

    question_id: str
    answer: str


class ResumeTriageRequest(BaseModel):
    """Body for ``POST /triage/sessions/{id}/resume``."""

    answers: list[PmAnswer] = Field(default_factory=list)
    override: bool = False


class SynthesisOutput(BaseModel):
    """Advisory output of the synthesis agent.

    Synthesis only emits this small, reliably-producible shape; the orchestrator
    owns assembling the final ``TriageReport``. ``verdict`` here is a suggestion
    that the orchestrator's deterministic rule may override.
    """

    verdict: Verdict
    raw_analysis: str = ""
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Estimation + Task Breakdown (D7 bonus)
# ---------------------------------------------------------------------------


class ConfidenceInterval(BaseModel):
    """Three-point estimate in engineer-days."""

    low: float = Field(..., ge=0)
    median: float = Field(..., ge=0)
    high: float = Field(..., ge=0)


class Estimate(BaseModel):
    """Output of the Estimation Agent."""

    point_estimate_days: float = Field(..., ge=0)
    confidence_interval: ConfidenceInterval
    drivers: list[str] = Field(
        default_factory=list,
        description="Factors that raised or lowered the estimate",
    )
    low_confidence: bool = False


class Ticket(BaseModel):
    """A single executable work item from the Task Breakdown Agent."""

    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    estimated_effort_days: float = Field(..., ge=0)
    dependencies: list[str] = Field(
        default_factory=list, description="Titles of tickets this depends on"
    )


class TaskBreakdownResult(BaseModel):
    """Output of the Task Breakdown Agent — wraps a list of Ticket."""

    tickets: list[Ticket] = Field(default_factory=list)
    total_estimated_effort_days: float = Field(0, ge=0)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


class AuditEntry(BaseModel):
    """One row in the pipeline audit trail."""

    stage: str = Field(
        ..., description="Pipeline stage: 'intake', 'policy', 'specialist', 'synthesis', ..."
    )
    status: Literal["running", "completed", "failed", "skipped"]
    agent_name: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Composite TriageReport (Contract: Orchestrator Workflow Graph)
# ---------------------------------------------------------------------------


class TriageReport(BaseModel):
    """Final composite output of the triage pipeline.

    Per design.md Contract: Orchestrator Workflow Graph — the orchestrator's
    ``triage(prd_id) -> TriageReport`` entry point produces this object.
    """

    prd_id: str
    verdict: Verdict
    status: Literal["completed", "awaiting_pm", "terminated"] = "completed"
    session_id: Optional[str] = Field(
        None,
        description="Set when status='awaiting_pm'; identifies the HITL session to resume.",
    )

    # Specialist outputs (None when that agent failed or didn't run)
    completeness: Optional[CompletenessReport] = None
    clarity: Optional[ClarityReport] = None
    architecture: Optional[ArchitectureReport] = None
    risk: Optional[RiskReport] = None
    failed_agents: list[FailedReport] = Field(default_factory=list)

    # Synthesis consolidation
    risk_register: list[Finding] = Field(default_factory=list)
    clarifying_questions: list[ClarifyingQuestion] = Field(default_factory=list)
    pm_responses: list[PmAnswer] = Field(default_factory=list)

    # Downstream stages (None when pipeline terminated before them)
    estimate: Optional[Estimate] = None
    tickets: list[Ticket] = Field(default_factory=list)

    # Audit + flags
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    hitl_overridden: bool = False
    policy_decision: Optional[PolicyDecision] = None


# ---------------------------------------------------------------------------
# HITL sessions (add-web-frontend)
# ---------------------------------------------------------------------------


class SessionNotFound(Exception):
    """Raised when a HITL session id does not exist or has expired.

    Raised by ``resume_triage`` and the HTTP resume/status endpoints to signal
    a 404 back to the caller.
    """


class SessionState(BaseModel):
    """Frozen snapshot of a paused triage, stored in ``SessionRegistry``.

    Holds everything ``resume_triage`` needs to finalise the report without
    re-running intake/policy/specialists: the original PRD content, the policy
    decision, and the partial report produced by synthesis (which carries the
    clarifying questions the PM must answer).
    """

    prd_id: str
    prd_content: str
    policy_decision: PolicyDecision
    partial_report: TriageReport
    created_at: datetime
    expires_at: datetime
