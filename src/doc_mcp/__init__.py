"""Document MCP server — exposes the PRD repository as MCP tools.

Module name is ``doc_mcp`` (not ``mcp``) to avoid shadowing the upstream
``mcp`` PyPI package during ``from mcp.server.fastmcp import FastMCP`` imports.
See design.md → Decision: Rename src/mcp to src/doc_mcp.
"""
