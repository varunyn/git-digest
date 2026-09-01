"""FastMCP v4 integration boundaries for the git-digest server."""

from __future__ import annotations

import asyncio

from fastmcp import Client

from git_updates.mcp.server import get_git_updates, list_tracked_repos, mcp


def test_fastmcp_v4_discovers_public_tools() -> None:
    """The FastMCP v4 server exposes the supported tool surface."""

    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} >= {
        "get_git_updates",
        "list_tracked_repos",
        "get_git_updates_data",
        "get_tracked_repositories",
    }


def test_fastmcp_v4_discovers_resources() -> None:
    """Stable resource URIs are discoverable without fetching repositories."""

    resources = asyncio.run(mcp.list_resources())

    assert {str(resource.uri) for resource in resources} >= {
        "git-digest://tracked-repositories",
        "git-digest://configuration-status",
    }


def test_list_tracked_repos_reads_config(tmp_path) -> None:
    config_path = tmp_path / "repos.yaml"
    config_path.write_text("repos:\n  - https://github.com/example/widget.git\n")

    result = list_tracked_repos(str(config_path))

    assert result == "https://github.com/example/widget.git"


def test_structured_repository_response_is_not_wrapped(tmp_path) -> None:
    """Typed output schemas preserve the public top-level JSON response shape."""
    config_path = tmp_path / "repos.yaml"
    config_path.write_text("repos: []\n")

    async def call_tool() -> dict:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "get_tracked_repositories", {"config_path": str(config_path)}
            )
            return result.structured_content

    assert asyncio.run(call_tool()) == {"status": "ok", "repositories": []}


def test_get_git_updates_validates_format_before_fetching(tmp_path) -> None:
    config_path = tmp_path / "repos.yaml"
    config_path.write_text("repos:\n  - https://github.com/example/widget.git\n")

    result = get_git_updates(str(config_path), output_format="csv")

    assert result == "Error: output_format must be text, markdown, or json."
