## ADDED Requirements

### Requirement: Pipeline SHALL accept PRD input via Document MCP

The triage pipeline SHALL ingest a target PRD by invoking the `get_prd` tool from the document-repository MCP server, then pass the PRD content through subsequent analysis stages. The pipeline SHALL NOT read PRD files directly from the filesystem.

#### Scenario: Valid PRD ingestion

- **WHEN** the pipeline is invoked with `prd_id: "prd-001"`
- **THEN** the orchestrator SHALL call `get_prd` via MCP, receive the PRD content, and proceed to the policy gate

#### Scenario: PRD not found

- **WHEN** the pipeline is invoked with an unknown `prd_id`
- **THEN** the orchestrator SHALL terminate the run and emit an error report containing the `prd_id` and a "not found" message, without entering analysis

### Requirement: Policy gate SHALL reject PRDs containing PII or secrets

Before any specialist agent reads the PRD, a policy check SHALL scan the document for personally identifiable information (email addresses, phone numbers, national IDs) and secret material (API keys, passwords, tokens matching known patterns). PRDs failing the check SHALL be rejected with a redaction report.

#### Scenario: PRD passes policy check

- **WHEN** a PRD containing no PII or secret patterns is evaluated by the policy gate
- **THEN** the pipeline SHALL proceed to the parallel specialist analysis stage

#### Scenario: PRD contains an API key pattern

- **WHEN** a PRD contains a string matching the regex `AIza[0-9A-Za-z_\-]{35}` (Google API key pattern)
- **THEN** the policy gate SHALL reject the PRD, emit a rejection report listing the detected pattern type and its location (line number), and SHALL NOT pass the content to any specialist agent

##### Example: policy gate decisions

| PRD Content | Decision | Report Contains |
| ----------- | -------- | --------------- |
| "Contact john@example.com for details" | REJECT | PII: email at line 12 |
| "API key: AIzaSyD-abc123...xyz" | REJECT | Secret: Google API key at line 8 |
| "The system supports OAuth 2.0" | ACCEPT | (no report) |

### Requirement: Four specialist agents SHALL analyze the PRD in parallel

The pipeline SHALL dispatch the PRD content concurrently to four specialist agents — Completeness Checker, Architecture Fit Assessor, Risk and Compliance Checker, and Clarity Checker — using ADK parallel orchestration. Each agent SHALL produce a structured report conforming to a shared schema before the synthesis stage begins.

#### Scenario: All four agents complete successfully

- **WHEN** the PRD passes the policy gate and is dispatched to all four specialist agents
- **THEN** the orchestrator SHALL wait for all four agents to return, then forward the four reports to the Synthesis Agent

#### Scenario: One specialist agent fails

- **WHEN** the Architecture Fit Assessor raises an exception during analysis
- **THEN** the orchestrator SHALL mark that agent's report as `failed` with the error message, proceed with the remaining three reports to synthesis, and SHALL NOT abort the entire pipeline

### Requirement: Completeness Checker SHALL verify PRD structural completeness

The Completeness Checker agent SHALL evaluate whether the PRD contains the required sections: user stories, acceptance criteria in Given/When/Then format, non-functional requirements, edge cases or error paths, and an explicit out-of-scope section. It SHALL output a completeness score (0-100) and a list of missing or insufficient sections with severity levels.

#### Scenario: Complete PRD

- **WHEN** a PRD contains all five required sections with sufficient detail
- **THEN** the Completeness Checker SHALL return a completeness score of 80 or higher and an empty missing-sections list

#### Scenario: PRD missing acceptance criteria

- **WHEN** a PRD lacks any Given/When/Then acceptance criteria
- **THEN** the Completeness Checker SHALL return a completeness score below 60 and the missing-sections list SHALL include an entry with `section: "acceptance_criteria"`, `severity: "high"`

### Requirement: Clarity Checker SHALL detect ambiguous terms and contradictions

The Clarity Checker agent SHALL scan the PRD for vague quantifiers (e.g., "fast", "scalable", "user-friendly" without metrics), internal contradictions, and undefined domain terms. It SHALL output a list of ambiguous items and a corresponding list of clarifying questions addressed to the PM.

#### Scenario: Vague term detected

- **WHEN** a PRD states "the system shall be fast" without a quantitative target
- **THEN** the Clarity Checker SHALL flag this as an ambiguous item of type `vague_quantifier` and generate a clarifying question such as "Define 'fast': what is the target p95 latency in milliseconds?"

##### Example: vague term detection

| PRD Phrase | Flag Type | Generated Question |
| ---------- | --------- | ------------------ |
| "fast response" | vague_quantifier | "Define target p95 latency (ms)" |
| "scalable" | vague_quantifier | "Define expected QPS and data volume at peak" |
| "user-friendly" | vague_quantifier | "Define measurable UX metric (e.g., SUS score threshold)" |

### Requirement: Synthesis Agent SHALL merge specialist reports into structured assessment

The Synthesis Agent SHALL consume the four specialist reports and produce a single `TriageReport` object containing: an overall triage verdict (`pass`, `needs_clarification`, `reject`), a consolidated risk register, a consolidated missing-items list, and the full list of clarifying questions. The synthesis SHALL weight critical-severity findings from the Risk agent as veto-capable.

#### Scenario: No critical risks and low ambiguity

- **WHEN** all four reports return with no critical-severity risks and fewer than 3 clarifying questions
- **THEN** the Synthesis Agent SHALL set `verdict: "pass"` and forward the report directly to estimation

#### Scenario: Critical risk detected

- **WHEN** the Risk and Compliance Checker reports any finding with `severity: "critical"`
- **THEN** the Synthesis Agent SHALL set `verdict: "needs_clarification"` regardless of other agents' findings, and SHALL route the report to the HITL gate

### Requirement: HITL gate SHALL pause pipeline and request PM clarification

When the synthesis verdict is `needs_clarification`, the pipeline SHALL enter a Human-in-the-Loop checkpoint: it SHALL emit the clarifying questions to the configured output channel, pause execution, and wait for PM responses. The pipeline SHALL NOT proceed to estimation until the PM provides responses or explicitly overrides the gate.

#### Scenario: PM provides clarifications

- **WHEN** the HITL gate emits 3 clarifying questions and the PM responds with answers to all 3
- **THEN** the pipeline SHALL resume, merge the PM responses into the PRD context, and proceed to the Estimation Agent

#### Scenario: PM overrides the gate

- **WHEN** the PM explicitly issues an override command at the HITL gate
- **THEN** the pipeline SHALL proceed to estimation, the final report SHALL flag `hitl_overridden: true`, and the risk register SHALL retain the original unmitigated findings

#### Scenario: HITL timeout

- **WHEN** the HITL gate waits longer than the configured timeout (default 24 hours) without a PM response
- **THEN** the pipeline SHALL emit a report with `verdict: "needs_clarification"`, `status: "awaiting_pm"`, and SHALL terminate the run without estimation

### Requirement: Estimation Agent SHALL produce effort estimate with confidence interval

After the pipeline passes synthesis (or HITL clarification), the Estimation Agent SHALL query `get_similar_prds` for historical analogues, compare the target PRD scope against them, and output a point estimate (in engineer-days) with a confidence interval (low, median, high) and a list of estimation drivers (factors that increase or decrease the estimate).

#### Scenario: Historical analogues available

- **WHEN** `get_similar_prds` returns 3 historical PRDs with known actual effort
- **THEN** the Estimation Agent SHALL produce a point estimate within the range of the historical data, a confidence interval, and SHALL list at least 2 estimation drivers referencing the historical analogues

#### Scenario: No historical analogues

- **WHEN** `get_similar_prds` returns zero results
- **THEN** the Estimation Agent SHALL produce a wider confidence interval (high minus low greater than 2x median) and SHALL flag `low_confidence: true` in the output

### Requirement: Task Breakdown Agent SHALL decompose PRD into executable tickets

The Task Breakdown Agent SHALL consume the clarified PRD and the effort estimate, then output a list of tickets, each with a title, description, acceptance criteria, estimated effort, and dependency graph. Tickets SHALL be granular enough to assign to a single engineer.

#### Scenario: Well-scoped PRD decomposition

- **WHEN** a PRD with verdict `pass` and a point estimate of 10 engineer-days is processed
- **THEN** the Task Breakdown Agent SHALL output between 3 and 8 tickets, each with a non-empty acceptance criteria field and an effort estimate summing to within 20% of the PRD-level estimate

### Requirement: Pipeline SHALL emit a structured Markdown report

Upon completion (or termination), the pipeline SHALL emit a Markdown report containing: the PRD identifier, the triage verdict, the consolidated risk register, the completeness assessment, the clarifying questions and PM responses (if any), the effort estimate, the ticket breakdown, and the full audit trail of which agents ran and their statuses.

#### Scenario: Successful full pipeline run

- **WHEN** the pipeline completes all stages from ingestion through task breakdown
- **THEN** the emitted report SHALL contain all eight sections populated with non-empty content, and the report file SHALL be valid Markdown parseable by any standard Markdown renderer

#### Scenario: Pipeline terminated early at HITL timeout

- **WHEN** the pipeline terminates due to HITL timeout before estimation
- **THEN** the emitted report SHALL contain populated sections for verdict, risk register, completeness, and clarifying questions, and SHALL mark the estimation and ticket-breakdown sections as `not_reached`

### Requirement: Pipeline SHALL be orchestrated via ADK workflow graph

The entire pipeline SHALL be implemented as an ADK 2.0 workflow graph containing: a parallel fan-out node (dispatching to four specialists), a join node (synthesis), a conditional edge (HITL gate branch), and sequential nodes (estimation, breakdown, output). The workflow definition SHALL be declarative and inspectable.

#### Scenario: Workflow graph structure validation

- **WHEN** the ADK workflow is serialized to its graph representation
- **THEN** the graph SHALL contain at least one parallel-execution segment, at least one conditional edge, and at least three sequential nodes, verifiable by inspecting the workflow's node and edge definitions

