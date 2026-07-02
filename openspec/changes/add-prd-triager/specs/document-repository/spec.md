## ADDED Requirements

### Requirement: MCP server SHALL expose document repository tools

The system SHALL implement an MCP (Model Context Protocol) server that exposes the PRD document repository and architecture documentation as callable tools, enabling both the triage pipeline and external MCP-compatible consumers to read documents through a standard protocol.

#### Scenario: MCP server starts and advertises tools

- **WHEN** the MCP server is started via stdio or SSE transport
- **THEN** the server SHALL advertise four tools: `list_prds`, `get_prd`, `get_architecture_context`, `get_similar_prds`

#### Scenario: MCP consumer discovers available tools

- **WHEN** an MCP client connects and sends a `tools/list` request
- **THEN** the server SHALL return a JSON array of tool definitions, each containing `name`, `description`, and `inputSchema` fields conforming to the MCP specification

### Requirement: list_prds tool SHALL return available PRD metadata

The `list_prds` tool SHALL return a list of all PRD documents stored in the configured `data/prds/` directory, including each document's identifier, title, status, and last-modified timestamp.

#### Scenario: Non-empty repository

- **WHEN** `list_prds` is called with no arguments and `data/prds/` contains 3 Markdown files
- **THEN** the tool SHALL return an array of 3 objects, each containing `id`, `title`, `status`, and `updated_at` fields

#### Scenario: Empty repository

- **WHEN** `list_prds` is called and `data/prds/` contains no documents
- **THEN** the tool SHALL return an empty array, not an error

##### Example: list_prds output shape

| Input | Expected Output | Notes |
| ----- | --------------- | ----- |
| `{}` | `[]` | empty repo |
| `{}` | `[{id: "prd-001", title: "Dark Mode", status: "draft", updated_at: "2026-06-28"}]` | one PRD |

### Requirement: get_prd tool SHALL return full PRD content by identifier

The `get_prd` tool SHALL accept a `prd_id` parameter and return the complete Markdown content of the corresponding PRD document, including its frontmatter and body.

#### Scenario: Valid identifier

- **WHEN** `get_prd` is called with `prd_id: "prd-001"` and a file named `prd-001.md` exists in `data/prds/`
- **THEN** the tool SHALL return an object containing `id`, `title`, `content` (full Markdown text), and `metadata` (parsed frontmatter)

#### Scenario: Unknown identifier

- **WHEN** `get_prd` is called with `prd_id: "nonexistent"`
- **THEN** the tool SHALL return an error response with a message indicating the PRD was not found, and SHALL NOT raise an unhandled exception

### Requirement: get_architecture_context tool SHALL return architecture knowledge base

The `get_architecture_context` tool SHALL return the current system architecture document (`data/architecture/architecture.md`) concatenated with the most recent Architecture Decision Records (ADRs) from `data/architecture/adr/`, enabling the Architecture Fit Assessor agent to evaluate PRD impact against the existing system.

#### Scenario: Architecture context with ADRs

- **WHEN** `get_architecture_context` is called with no arguments
- **THEN** the tool SHALL return an object containing `architecture_doc` (full content of architecture.md) and `adrs` (array of the 5 most recent ADRs, each with `id`, `title`, `status`, and `content`)

#### Scenario: No ADRs available

- **WHEN** `get_architecture_context` is called and `data/architecture/adr/` is empty
- **THEN** the tool SHALL return `architecture_doc` populated and `adrs` as an empty array

### Requirement: get_similar_prds tool SHALL return semantically similar historical PRDs

The `get_similar_prds` tool SHALL accept a `query` string and optional `top_k` integer (default 3), perform semantic search over historical PRDs using vector embeddings, and return the top-k most similar documents with similarity scores.

#### Scenario: Semantic search returns ranked results

- **WHEN** `get_similar_prds` is called with `query: "add authentication to mobile app"` and `top_k: 3`
- **THEN** the tool SHALL return an array of up to 3 objects, each containing `id`, `title`, `similarity_score` (float between 0.0 and 1.0), sorted by descending similarity score

##### Example: similarity ranking

- **GIVEN** historical PRDs: A "OAuth login" (score 0.91), B "Payment gateway" (score 0.32), C "SSO integration" (score 0.85)
- **WHEN** `get_similar_prds` is called with `query: "add authentication"` and `top_k: 2`
- **THEN** results SHALL be `[A (0.91), C (0.85)]` in that order

#### Scenario: top_k exceeds available documents

- **WHEN** `get_similar_prds` is called with `top_k: 10` but only 4 historical PRDs exist
- **THEN** the tool SHALL return all 4 documents ranked by similarity, not an error

### Requirement: MCP server SHALL persist vector search index across restarts

The system SHALL build and persist a vector search index over the PRD repository to support `get_similar_prds`, and SHALL rebuild the index incrementally when documents are added or modified, avoiding full rebuilds on every server start.

#### Scenario: Cold start with existing index

- **WHEN** the MCP server starts and a valid persisted index file exists at `openspec/.vector-search.db`
- **THEN** the server SHALL load the existing index without rebuilding, achieving startup in under 5 seconds for a repository of up to 100 documents

#### Scenario: New document added after initial index build

- **WHEN** a new PRD file is added to `data/prds/` after the index was built
- **THEN** the next call to `get_similar_prds` SHALL reflect the new document, and the index SHALL be updated incrementally rather than fully rebuilt

