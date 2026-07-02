"""End-to-end MCP integration test — real client connects to real server.

Verifies the MCP Key Concept by spawning the actual Document MCP server as a
subprocess and connecting via the MCP stdio protocol. This is NOT a mock test —
it exercises the real FastMCP server, real stdio transport, and real JSON-RPC.

Does NOT require GOOGLE_API_KEY: the 3 file-based tools (list_prds, get_prd,
get_architecture_context) work offline. get_similar_prds uses keyword fallback.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_mcp_client_can_connect_and_list_tools():
    """A real MCP client connects to the server and discovers 4 tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    project_root = Path(__file__).resolve().parent.parent
    server_params = StdioServerParameters(
        command=str(Path.home() / ".local" / "bin" / "uv"),
        args=[
            "run",
            "--directory",
            str(project_root),
            "python",
            "-m",
            "doc_mcp.server",
        ],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List tools
            tools_result = await session.list_tools()
            tool_names = {t.name for t in tools_result.tools}
            assert tool_names == {
                "list_prds",
                "get_prd",
                "get_architecture_context",
                "get_similar_prds",
            }, f"Expected 4 tools, got: {tool_names}"

            # Each tool must have a description and input schema
            for tool in tools_result.tools:
                assert tool.description, f"{tool.name} missing description"
                assert tool.inputSchema is not None, f"{tool.name} missing inputSchema"


@pytest.mark.asyncio
async def test_mcp_client_can_call_list_prds():
    """Client calls list_prds and gets 5 ShopFlow PRDs back."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    project_root = Path(__file__).resolve().parent.parent
    server_params = StdioServerParameters(
        command=str(Path.home() / ".local" / "bin" / "uv"),
        args=[
            "run",
            "--directory",
            str(project_root),
            "python",
            "-m",
            "doc_mcp.server",
        ],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("list_prds", {})
            assert len(result.content) > 0

            # FastMCP may return each list element as a separate TextContent,
            # or the whole list as one TextContent. Handle both.
            import json
            all_prds = []
            for item in result.content:
                if hasattr(item, "text"):
                    data = json.loads(item.text)
                    if isinstance(data, list):
                        all_prds = data
                        break
                    elif isinstance(data, dict):
                        all_prds.append(data)
            assert len(all_prds) == 5
            ids = {p["id"] for p in all_prds}
            assert ids == {"prd-001", "prd-002", "prd-003", "prd-004", "prd-005"}


@pytest.mark.asyncio
async def test_mcp_client_can_call_get_prd():
    """Client calls get_prd("prd-001") and gets full content."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    project_root = Path(__file__).resolve().parent.parent
    server_params = StdioServerParameters(
        command=str(Path.home() / ".local" / "bin" / "uv"),
        args=[
            "run",
            "--directory",
            str(project_root),
            "python",
            "-m",
            "doc_mcp.server",
        ],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            result = await session.call_tool("get_prd", {"prd_id": "prd-001"})
            import json
            text_content = result.content[0]
            prd = json.loads(text_content.text if hasattr(text_content, "text") else str(text_content))
            assert prd["id"] == "prd-001"
            assert "Dark Mode" in prd["title"]
            assert "User Stories" in prd["content"]
