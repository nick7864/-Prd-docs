## ADDED Requirements

### Requirement: Triage entry point SHALL expose synchronous API

The `triage(prd_id) -> TriageReport` function SHALL remain a synchronous (non-coroutine) callable so existing callers — `eval/judge.py`, the FastAPI handler in `src/main.py`, and the Antigravity Skill — invoke it without `await` or `asyncio.run`. The asynchronous execution of the underlying ADK pipeline SHALL be fully encapsulated inside `triage()`.

#### Scenario: Synchronous call from non-async caller

- **WHEN** `eval/judge.py` calls `report = triage("prd-001")` at module top level (no event loop running)
- **THEN** the call returns a `TriageReport` instance (not a coroutine)
- **AND** no `RuntimeWarning: coroutine ... was never awaited` is emitted on stderr

#### Scenario: FastAPI handler stays synchronous

- **WHEN** `src/main.py`'s `@app.post("/triage")` handler calls `triage(prd_id)` directly
- **THEN** the handler does not need to be declared `async def` solely because of this call
- **AND** the response JSON contains a fully-populated `verdict` field

### Requirement: ADK pipeline SHALL await async session service calls

The internal `_run_adk_pipeline(prd_id, prd_content)` function SHALL `await` every coroutine returned by `InMemorySessionService.create_session` and `InMemorySessionService.get_session`. Calling these methods without `await` is a correctness defect because ADK 2.x ships them as coroutines that return `Session` objects when awaited.

#### Scenario: create_session awaited

- **WHEN** `_run_adk_pipeline` requests a new session via `session_service.create_session(app_name=..., user_id=...)`
- **THEN** the returned object is a `Session` instance (not a coroutine)
- **AND** accessing `.id` on the next line does not raise `AttributeError: 'coroutine' object has no attribute 'id'`

#### Scenario: get_session awaited

- **WHEN** `_run_adk_pipeline` retrieves the final session via `session_service.get_session(...)`
- **THEN** the returned object is a `Session` instance whose `.state` dict can be read
- **AND** `state.get("triage_report")` returns the synthesis agent's output

#### Scenario: Runner.run iterator stays synchronous

- **WHEN** `_run_adk_pipeline` consumes events from `runner.run(user_id=..., session_id=..., new_message=...)`
- **THEN** the event consumption loop SHALL NOT `await` the iterator (Runner.run is a synchronous generator in ADK 2.x)
- **AND** awaiting it would itself raise a `TypeError`

### Requirement: Pipeline failure mode SHALL preserve observable audit trail

When the ADK pipeline raises after `triage()` has already done intake + policy gate, `triage()` SHALL catch the exception, append an `AuditEntry(stage="specialists", status="failed", error=str(exc))` to `audit_trail`, and return a `TriageReport` with `verdict=NEEDS_CLARIFICATION` and `status="terminated"`. This preserves the existing observable contract for callers; the async refactor SHALL NOT change this failure shape.

#### Scenario: Exception during pipeline becomes failed audit entry

- **WHEN** any exception is raised inside the awaited `_run_adk_pipeline` call
- **THEN** `triage()` returns rather than propagating
- **AND** the returned `TriageReport.audit_trail` contains an entry with `stage="specialists"`, `status="failed"`
- **AND** the returned `TriageReport.policy_decision` reflects the actual policy gate decision (not `None`)
