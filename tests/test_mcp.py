"""FastMCP v3 integration boundaries for the git-digest server."""

from __future__ import annotations

import asyncio

from git_updates.mcp.server import get_git_updates, list_tracked_repos, mcp


def test_fastmcp_v3_discovers_public_tools() -> None:
    """The FastMCP v3 server exposes the supported tool surface."""

    tools = asyncio.run(mcp.list_tools())

    assert {tool.name for tool in tools} >= {
        "get_git_updates",
        "list_tracked_repos",
        "get_git_updates_data",
        "get_tracked_repositories",
    }


def test_fastmcp_v3_discovers_resources() -> None:
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


def test_get_git_updates_validates_format_before_fetching(tmp_path) -> None:
    config_path = tmp_path / "repos.yaml"
    config_path.write_text("repos:\n  - https://github.com/example/widget.git\n")

    result = get_git_updates(str(config_path), output_format="csv")

    assert result == "Error: output_format must be text, markdown, or json."
