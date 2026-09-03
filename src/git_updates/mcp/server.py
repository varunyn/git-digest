"""MCP server implementation: FastMCP app and tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from typing_extensions import TypedDict

from git_updates.config import DEFAULT_CONFIG_PATHS, Config, load_dotenv_for_app
from git_updates.service import collect_updates
from git_updates.summary import format_report, format_report_with_ai

mcp = FastMCP(
    "Git Updates",
    instructions=(
        "Fetch recent Git commits and releases from configured repositories. "
        "Use get_git_updates_data when structured output is useful, or get_git_updates "
        "when a rendered text, Markdown, or JSON report is needed."
    ),
)


class CommitData(TypedDict):
    """Machine-readable commit data returned by the updates tool."""

    sha: str
    author: str
    date: str
    subject: str
    refs: str
    type: str | None


class TagData(TypedDict):
    """Machine-readable release tag data returned by the updates tool."""

    name: str
    sha: str
    date: str
    message: str


class RepositoryUpdateData(TypedDict):
    """Machine-readable update data for one repository."""

    name: str
    url: str
    branch: str
    status: Literal["ok", "error"]
    error: str | None
    since_last_run: bool
    tags_since_last_run: bool
    head_sha: str | None
    newest_tag_date: str | None
    signals: list[str]
    commits: list[CommitData]
    tags: list[TagData]


class UpdateCounts(TypedDict):
    """Aggregate counts included in a machine-readable update report."""

    repositories: int
    changed_repositories: int
    commits: int
    tags: int
    errors: int


class GitUpdatesData(TypedDict, total=False):
    """Machine-readable update report or report-generation error.

    Fields are optional because successful reports and errors intentionally have
    different stable top-level shapes. Keeping this as one object schema avoids
    FastMCP wrapping union results under a ``result`` key.
    """

    schema_version: Literal[1]
    title: str | None
    generated_at: str
    summary: UpdateCounts
    repositories: list[RepositoryUpdateData]
    status: Literal["error"]
    error: str


class TrackedRepositoryData(TypedDict):
    """Machine-readable configuration for one tracked repository."""

    url: str
    branch: str
    max_commits: int
    include_tags: bool


class TrackedRepositoriesData(TypedDict, total=False):
    """Machine-readable tracked repository response or configuration error."""

    status: Literal["ok", "error"]
    repositories: list[TrackedRepositoryData]
    error: str


def _load_config(config_path: str | None) -> Config:
    """Load a config, apply env overrides, and fail if no config exists."""
    load_dotenv_for_app()
    if config_path:
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        return Config.from_yaml(path).with_env_overrides()
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return Config.from_yaml(p).with_env_overrides()
    raise FileNotFoundError(
        f"No config found. Create one of: {', '.join(str(p) for p in DEFAULT_CONFIG_PATHS)}"
    )


@mcp.tool(
    annotations=ToolAnnotations(
        # Fetching repositories updates the local clone cache; changes_only also
        # persists the last-seen state used by later runs.
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def get_git_updates(
    config_path: str | None = None,
    changes_only: bool = False,
    use_ai_summary: bool = False,
    ollama_model: str | None = None,
    title: str | None = None,
    output_format: str = "text",
) -> str:
    """
    Fetch latest git updates from configured repos and return a summary report.

    Uses the same repos.yaml (or given config_path) as the git-digest CLI. Returns
    plain text: recent commits and tags per repo, or an AI-generated digest if
    use_ai_summary is True (requires Ollama running locally).
    Defaults for title and ollama_model come from the config file or .env.

    Args:
        config_path: Optional path to repos.yaml. If omitted, uses current dir or
            ~/.config/git-digest/repos.yaml.
        changes_only: If True, only show commits new since last run (persists state
            in cache dir).
        use_ai_summary: If True, use Ollama to generate a short AI digest instead of
            raw commit list.
        ollama_model: Ollama model name when use_ai_summary is True.
        title: Report title (default: from config or GIT_DIGEST_DEFAULT_TITLE).
        output_format: One of text, markdown, or json. AI summaries support text only.

    Returns:
        The full report as a string (markdown-friendly text).
    """
    try:
        config = _load_config(config_path)
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error loading config: {e}"

    config.cache_dir.mkdir(parents=True, exist_ok=True)
    if output_format not in {"text", "markdown", "json"}:
        return "Error: output_format must be text, markdown, or json."
    if use_ai_summary and output_format != "text":
        return "Error: AI summaries support output_format text only."

    summaries = collect_updates(config, changes_only=changes_only)

    report_title = title if title is not None else config.default_title
    model = ollama_model if ollama_model is not None else config.ollama_model
    if use_ai_summary:
        report = format_report_with_ai(
            summaries,
            title=report_title,
            ollama_base_url=config.ollama_url,
            ollama_model=model,
            ollama_timeout=config.ollama_timeout,
        )
    else:
        report = format_report(summaries, title=report_title, output_format=output_format)

    return report


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def list_tracked_repos(config_path: str | None = None) -> str:
    """
    List repository URLs currently tracked by git-digest config.

    Args:
        config_path: Optional path to repos.yaml. If omitted, uses default locations.

    Returns:
        Newline-separated list of repo URLs, or an error message.
    """
    try:
        config = _load_config(config_path)
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error loading config: {e}"

    if not config.repos:
        return "No repos configured."
    return "\n".join(r.url for r in config.repos)


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    )
)
def get_git_updates_data(
    config_path: str | None = None,
    changes_only: bool = False,
) -> GitUpdatesData:
    """Fetch updates and return FastMCP v4 structured data.

    This is the machine-readable companion to ``get_git_updates``. It exposes
    the stable JSON report as a typed tool result rather than requiring clients
    to parse text content.
    """
    report = get_git_updates(
        config_path=config_path,
        changes_only=changes_only,
        output_format="json",
    )
    try:
        return json.loads(report)
    except json.JSONDecodeError:
        return {"schema_version": 1, "status": "error", "error": report}


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )
)
def get_tracked_repositories(config_path: str | None = None) -> TrackedRepositoriesData:
    """Return tracked repositories as structured data for programmatic clients."""
    try:
        config = _load_config(config_path)
    except Exception as e:
        return {"status": "error", "repositories": [], "error": str(e)}
    return {
        "status": "ok",
        "repositories": [
            {
                "url": repo.url,
                "branch": repo.branch,
                "max_commits": repo.max_commits,
                "include_tags": repo.include_tags,
            }
            for repo in config.repos
        ],
    }


@mcp.resource(
    "git-digest://tracked-repositories",
    name="tracked_repositories",
    description="The currently configured repositories in JSON format.",
    mime_type="application/json",
)
def tracked_repositories_resource() -> str:
    """Expose the active repository configuration as a FastMCP resource."""
    return json.dumps(get_tracked_repositories(), indent=2, sort_keys=True)


@mcp.resource(
    "git-digest://configuration-status",
    name="configuration_status",
    description="Whether git-digest can load its active configuration.",
    mime_type="application/json",
)
def configuration_status_resource() -> str:
    """Expose a lightweight configuration health resource without fetching remotes."""
    try:
        config = _load_config(None)
    except Exception as e:
        status: dict[str, Any] = {"status": "error", "error": str(e)}
    else:
        status = {"status": "ok", "repository_count": len(config.repos)}
    return json.dumps(status, indent=2, sort_keys=True)


def run() -> None:
    """Run over stdio (default) or FastMCP v4 Streamable HTTP."""
    parser = argparse.ArgumentParser(description="Run the git-digest FastMCP v4 server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport. 'http' starts FastMCP's Streamable HTTP server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000).")
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    run()
