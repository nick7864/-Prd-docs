# PRD Triage Agent

Multi-agent pipeline that triages Product Requirement Documents (PRDs) before
engineering begins. Built for the Google × Kaggle AI Agents Capstone (Track:
Agents for Business).

## MCP Tools (document-repository server)

This project ships a stdio MCP server (`doc_mcp/server.py`) exposing 5 tools:

| Tool | What it does |
|---|---|
| `list_prds` | List all sample PRDs with metadata |
| `get_prd(prd_id)` | Read a single PRD's full content |
| `get_architecture_context` | Get the ShopFlow system architecture + 3 ADRs |
| `get_similar_prds(query)` | Semantic search for similar historical PRDs |
| `triage_prd(prd_id)` | **Run the full triage pipeline** (policy gate → 4 specialist agents → synthesis) and return a TriageReport |

## Demo PRDs

| ID | Scenario | Expected verdict |
|---|---|---|
| `prd-003` | Payment PRD with embedded API key | `reject` (policy gate, instant — no LLM needed) |
| `prd-001` | Complete dark-mode PRD | `pass` or `needs_clarification` (full LLM analysis) |
| `prd-002` | Wishlist PRD missing acceptance criteria | `needs_clarification` |

**Quick demo**: call `triage_prd("prd-003")` — returns instantly with a policy
rejection (demonstrates the Security/policy-gate feature without needing an
LLM API key).

## How to trigger from chat

Say any of: "triage prd-003", "analyze the dark mode PRD", "review prd-001",
"list available PRDs", "is prd-002 ready for engineering?".

---

<!-- SPECTRA:START v1.0.2 -->

# Spectra Instructions

This project uses Spectra for Spec-Driven Development(SDD). Specs live in `openspec/specs/`, change proposals in `openspec/changes/`.

## Use `/spectra-*` skills when:

- A discussion needs structure before coding → `/spectra-discuss`
- User wants to plan, propose, or design a change → `/spectra-propose`
- Tasks are ready to implement → `/spectra-apply`
- There's an in-progress change to continue → `/spectra-ingest`
- User asks about specs or how something works → `/spectra-ask`
- Implementation is done → `/spectra-archive`
- Commit only files related to a specific change → `/spectra-commit`

## Workflow

discuss? → propose → apply ⇄ ingest → archive

- `discuss` is optional — skip if requirements are clear
- Requirements change mid-work? Plan mode → `ingest` → resume `apply`

## Parked Changes

Changes can be parked（暫存）— temporarily moved out of `openspec/changes/`. Parked changes won't appear in `spectra list` but can be found with `spectra list --parked`. To restore: `spectra unpark <name>`. The `/spectra-apply` and `/spectra-ingest` skills handle parked changes automatically.

<!-- SPECTRA:END -->
