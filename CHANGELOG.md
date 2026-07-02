# Changelog

All notable changes to PRD Triage Agent are documented in this file.
This project follows Spec-Driven Development (Spectra) — the canonical
spec lives in `openspec/changes/add-prd-triager/`.

## [Unreleased] — add-prd-triager (2026-06-28 → 2026-07-06)

### Added

- **Document MCP Server** (`src/doc_mcp/`): FastMCP server exposing 4 tools
  (`list_prds`, `get_prd`, `get_architecture_context`, `get_similar_prds`)
  over stdio transport. Embedding-based semantic search with keyword-overlap
  fallback when `GOOGLE_API_KEY` is unset.
- **Four specialist agents** (`src/agents/`):
  - Completeness Checker — evaluates 5 required PRD sections (user stories,
    Given/When/Then AC, NFRs, edge cases, out-of-scope)
  - Clarity Checker — flags vague quantifiers, contradictions, undefined terms
  - Architecture Fit Assessor — reads architecture doc + ADRs via MCP tool
  - Risk & Compliance Checker — security, GDPR, PCI-DSS, performance risks
- **Synthesis Agent**: merges specialist reports into structured TriageReport
  with verdict (pass / needs_clarification / reject).
- **Orchestrator** (`src/agents/orchestrator.py`): ADK SequentialAgent →
  ParallelAgent(4 specialists) → Synthesis. Entry point: `triage(prd_id)`.
- **Policy Gate** (`src/policy/`): 10 regex rules (Google API keys, AWS keys,
  GitHub tokens, Stripe keys, emails, phones, JWTs, PEM private keys) in
  human-reviewable YAML. `check_policy()` returns `PolicyDecision`.
- **Critical-risk veto**: deterministic post-check — if any Risk finding is
  `critical`, forces `verdict=needs_clarification` regardless of LLM output.
  Safety-critical decisions must be predictable, not LLM-dependent.
- **HITL Gate**: synchronous CLI fallback. Pauses pipeline on
  `needs_clarification`, presents clarifying questions to PM, resumes on
  answers or override.
- **Estimation + Task Breakdown agents** (D7 bonus): effort estimation via
  vector-similarity retrieval of historical PRDs; ticket decomposition into
  3-8 executable work items.
- **Markdown Report Writer** (`src/report.py`): 8-section structured report
  (policy, completeness, clarity, risk register, clarifying questions, PM
  responses, estimate, tickets) + audit trail.
- **FastAPI Server** (`src/main.py`): `POST /triage`, `GET /health` endpoints
  for Cloud Run deployment.
- **Custom Skill** (`.agents/skills/prd-analysis/SKILL.md`): Level 3
  procedural skill for triggering triage from Antigravity.
- **5 Sample ShopFlow PRDs** (`data/prds/`): complete, missing-AC,
  API-key-contaminated, vague-terms, well-scoped.
- **Architecture doc + 3 ADRs** (`data/architecture/`): microservices split,
  PostgreSQL choice, OAuth2+PKCE auth.
- **Spectra spec** (`openspec/changes/add-prd-triager/`): proposal + design
  (12 Decisions, 5 Implementation Contracts) + tasks (29/30 done) + 2 delta
  specs (10+6 Requirements with Given/When/Then scenarios).
- **Deployment scripts** (`scripts/deploy.sh`, `scripts/demo.sh`).
- **Dockerfile** + `.dockerignore` for Cloud Run deployment.
- **Comprehensive README** with architecture diagram, setup, demo cases,
  deployment instructions.
- **Kaggle Writeup draft** (`WRITEUP.md`): 1,205 words (limit: 2,500).

### Design Decisions (12 total, see `design.md`)

1. Document MCP Server via FastMCP (not raw `mcp` package)
2. Four specialist agents as LlmAgent with Pydantic structured output
3. ADK Parallel workflow for specialist fan-out
4. Synthesis Agent with critical-risk veto (hybrid LLM + deterministic)
5. HITL gate via synchronous CLI (fallback from InteractiveCallback)
6. Policy gate via regex patterns + optional LLM semantic layer
7. Estimation via vector similarity retrieval
8. Phased delivery (MVP → strengthen → bonus)
9. Deployment via Dockerfile + Cloud Run
10. ADK CLI toolchain correction (`agents-cli` → `adk`)
11. Antigravity showcase strategy (3 video touchpoints)
12. Rename `src/mcp/` → `src/doc_mcp/` (namespace collision fix)

### Test Coverage

- **110 tests passing**, 4 skipped (integration tests requiring `GOOGLE_API_KEY`)
- MCP Server: 14 tests (4 tools + registration + edge cases)
- Pydantic Schemas: 20 tests (15 models, round-trip serialization)
- Policy Gate: 13 tests (10 rules + scanner error + edge cases)
- Markdown Report: 17 tests (8 sections + file I/O + all verdict paths)
- Agent Structure: 25 tests (graph structure + config + import verification)
- Orchestrator: 13 tests (veto logic + HITL gate + entry point paths)
- FastAPI: 8 tests (health + triage endpoint + all 5 PRDs + validation)
- Pipeline Integration: 6 tests (mocked end-to-end wiring)
