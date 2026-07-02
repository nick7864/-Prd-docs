"""Tests for the Document MCP Server (repository layer + tool wrappers).

Targets the four tools listed in the spec contract:
- list_prds (empty + populated)
- get_prd (valid + unknown id)
- get_architecture_context (with ADRs)
- get_similar_prds (ranking + top_k overflow + no-API-key fallback)

The embedding path requires ``GOOGLE_API_KEY``; tests use the keyword-fallback
path by deleting the env var, which exercises the same ranking contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Make src/ importable when running pytest from Project root
SRC = Path(__file__).resolve().parent.parent / "src"
import sys

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from doc_mcp import repository  # noqa: E402
from doc_mcp.repository import (  # noqa: E402
    get_architecture_context,
    get_prd,
    get_similar_prds,
    list_prds,
)


# ---------------------------------------------------------------------------
# list_prds
# ---------------------------------------------------------------------------


def test_list_prds_empty(tmp_path, monkeypatch):
    """Empty data/prds/ returns [], not an error."""
    monkeypatch.setattr(repository, "PRDS_DIR", tmp_path)
    assert list_prds() == []


def test_list_prds_with_files():
    """Default data/prds/ has 5 PRDs with full metadata."""
    result = list_prds()
    assert len(result) == 5
    ids = {p["id"] for p in result}
    assert ids == {"prd-001", "prd-002", "prd-003", "prd-004", "prd-005"}
    for entry in result:
        assert entry["title"], f"{entry['id']} missing title"
        assert entry["status"], f"{entry['id']} missing status"
        assert entry["updated_at"], f"{entry['id']} missing updated_at"


# ---------------------------------------------------------------------------
# get_prd
# ---------------------------------------------------------------------------


def test_get_prd_valid():
    """get_prd with known id returns full content + metadata."""
    result = get_prd("prd-001")
    assert result["id"] == "prd-001"
    assert "Dark Mode" in result["title"]
    assert "User Stories" in result["content"]
    assert result["metadata"]["status"] == "approved"
    assert result["metadata"]["updated_at"] == "2026-06-15"


def test_get_prd_unknown():
    """get_prd with unknown id returns error dict, not exception."""
    result = get_prd("nonexistent-id")
    assert "error" in result
    assert "nonexistent-id" in result["error"]


def test_get_prd_by_frontmatter_id_not_filename():
    """get_prd resolves by frontmatter id even when filename differs.

    prd-001 lives in prd-001-dark-mode.md; the loader must find it via
    frontmatter scan when the direct filename miss occurs.
    """
    result = get_prd("prd-003")  # file is prd-003-payment-with-key.md
    assert result["id"] == "prd-003"
    assert "Stripe" in result["title"]


# ---------------------------------------------------------------------------
# get_architecture_context
# ---------------------------------------------------------------------------


def test_get_architecture_context():
    """Architecture context has architecture_doc + 3 ADRs."""
    result = get_architecture_context()
    assert "architecture_doc" in result
    assert "ShopFlow" in result["architecture_doc"]
    assert "Services" in result["architecture_doc"]

    assert len(result["adrs"]) == 3
    adr_ids = {a["id"] for a in result["adrs"]}
    assert adr_ids == {"ADR-001", "ADR-002", "ADR-003"}
    for adr in result["adrs"]:
        assert adr["title"], f"{adr['id']} missing title"
        assert adr["status"] == "accepted"
        assert "Context" in adr["content"]
        assert "Decision" in adr["content"]


def test_get_architecture_context_no_adrs(tmp_path, monkeypatch):
    """Empty ADR dir still returns architecture_doc + adrs: []."""
    monkeypatch.setattr(repository, "ADR_DIR", tmp_path)
    result = get_architecture_context()
    assert result["architecture_doc"]  # still populated
    assert result["adrs"] == []


# ---------------------------------------------------------------------------
# get_similar_prds — keyword fallback path (no API key)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """Force keyword fallback for all tests in this module.

    The embedding path is integration-tested separately once GOOGLE_API_KEY
    is provisioned; unit tests must not depend on network or credentials.
    """
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_get_similar_prds_no_api_key_returns_list():
    """Without API key, falls back to keyword matching (still returns ranked list)."""
    result = get_similar_prds("dark mode theme ui", top_k=3)
    assert isinstance(result, list)
    assert len(result) <= 3
    for r in result:
        assert "similarity_score" in r
        assert 0.0 <= r["similarity_score"] <= 1.0


def test_get_similar_prds_ranking():
    """get_similar_prds ranks by relevance — payment-related query → prd-003 first."""
    result = get_similar_prds("payment stripe checkout integration", top_k=3)
    assert len(result) >= 1
    assert result[0]["id"] == "prd-003", (
        f"expected prd-003 first, got {result[0]['id']} "
        f"(scores: {[(r['id'], r['similarity_score']) for r in result]})"
    )


def test_get_similar_prds_top_k_exceeds_available():
    """top_k > available returns all without error."""
    result = get_similar_prds("test query", top_k=100)
    assert len(result) <= 5  # we only have 5 PRDs
    for r in result:
        assert "similarity_score" in r


def test_get_similar_prds_empty_query():
    """Empty or stopword-only query does not crash."""
    result = get_similar_prds("", top_k=3)
    assert isinstance(result, list)


def test_get_similar_prds_top_k_zero():
    """top_k=0 returns empty list."""
    result = get_similar_prds("payment", top_k=0)
    assert result == []


def test_get_similar_prds_no_prds(tmp_path, monkeypatch):
    """Empty repository returns [] for similarity queries."""
    monkeypatch.setattr(repository, "PRDS_DIR", tmp_path)
    result = get_similar_prds("anything", top_k=3)
    assert result == []


# ---------------------------------------------------------------------------
# MCP server tool registration smoke test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_server_advertises_four_tools():
    """FastMCP server registers all four tools with non-empty schemas."""
    from doc_mcp.server import mcp as mcp_server

    # FastMCP exposes tools via async list_tools on the underlying server.
    tools = await mcp_server.list_tools()
    tool_names = {t.name for t in tools}
    assert tool_names == {
        "list_prds",
        "get_prd",
        "get_architecture_context",
        "get_similar_prds",
    }
    for tool in tools:
        assert tool.description, f"{tool.name} missing description"
        assert tool.inputSchema is not None, f"{tool.name} missing inputSchema"
