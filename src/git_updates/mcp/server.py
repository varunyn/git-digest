"""MCP server implementation: FastMCP app and tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from git_updates.config import DEFAULT_CONFIG_PATHS, Config, load_dotenv_for_app
from git_updates.fetcher import fetch_repo_summary
from git_updates.state import (
    get_last_seen_newest_tag_date,
    get_last_seen_sha,
    get_last_seen_tag_ids,
    load_state,
    save_state,
    state_lock,
)
from git_updates.summary import format_report, format_report_with_ai

mcp = FastMCP(
    "Git Updates",
    instructions=(
        "Fetch recent Git commits and releases from configured repositories. "
        "Use get_git_updates_data when structured output is useful, or get_git_updates "
        "when a rendered text, Markdown, or JSON report is needed."
    ),
)


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
    annotations={
        # Fetching repositories updates the local clone cache; changes_only also
        # persists the last-seen state used by later runs.
        "readOnlyHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    }
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

    def collect_updates(state: dict) -> list:
        summaries = []
        for repo_config in config.repos:
            last_sha = get_last_seen_sha(state, repo_config.url) if changes_only else None
            last_tag_ids = get_last_seen_tag_ids(state, repo_config.url) if changes_only else None
            last_newest_tag_date = (
                get_last_seen_newest_tag_date(state, repo_config.url) if changes_only else None
            )
            summary = fetch_repo_summary(
                repo_config,
                config.cache_dir,
                last_seen_sha=last_sha,
                last_seen_tag_ids=last_tag_ids,
                last_seen_newest_tag_date=last_newest_tag_date,
            )
            summaries.append(summary)
            if changes_only and not summary.error and not summary.commits_truncated:
                entry = {}
                if summary.head_sha:
                    entry["commit_sha"] = summary.head_sha
                if summary.newest_tag_date:
                    entry["newest_tag_date"] = summary.newest_tag_date
                if repo_config.include_tags:
                    entry["tag_ids"] = summary.tag_ids
                if entry:
                    state[repo_config.url] = entry
        return summaries

    if changes_only:
        with state_lock(config.cache_dir):
            state = load_state(config.cache_dir)
            summaries = collect_updates(state)
            save_state(config.cache_dir, state)
    else:
        summaries = collect_updates({})

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
    annotations={
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
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


@mcp.tool()
def get_git_updates_data(
    config_path: str | None = None,
    changes_only: bool = False,
) -> dict[str, Any]:
    """Fetch updates and return FastMCP v3 structured data.

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
    annotations={
        "readOnlyHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
)
def get_tracked_repositories(config_path: str | None = None) -> dict[str, Any]:
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
    """Run over stdio (default) or FastMCP v3 Streamable HTTP."""
    parser = argparse.ArgumentParser(description="Run the git-digest FastMCP v3 server.")
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
