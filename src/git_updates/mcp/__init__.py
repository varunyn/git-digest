"""MCP server for git-digest: expose tools so any AI can fetch git update summaries."""

from __future__ import annotations

from git_updates.mcp.server import run

__all__ = ["run"]
