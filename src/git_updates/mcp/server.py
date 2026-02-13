"""MCP server implementation: FastMCP app and tools."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from git_updates.config import Config, DEFAULT_CONFIG_PATHS, load_dotenv_for_app
from git_updates.fetcher import fetch_repo_summary
from git_updates.state import (
    get_last_seen_sha,
    get_last_seen_tag_names,
    load_state,
    save_state,
)
from git_updates.summary import format_report, format_report_with_ai

mcp = FastMCP(
    "Git Updates",
    "Fetch latest git updates from configured repos and generate summaries.",
)


def _load_config(config_path: str | None) -> Config:
    """Load config from path or default locations; apply env overrides. Raises FileNotFoundError if none found."""
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


@mcp.tool()
def get_git_updates(
    config_path: str | None = None,
    changes_only: bool = False,
    use_ai_summary: bool = False,
    ollama_model: str | None = None,
    title: str | None = None,
) -> str:
    """
    Fetch latest git updates from configured repos and return a summary report.

    Uses the same repos.yaml (or given config_path) as the git-digest CLI. Returns
    plain text: recent commits and tags per repo, or an AI-generated digest if
    use_ai_summary is True (requires Ollama running locally).
    Defaults for title and ollama_model come from config file or .env (OLLAMA_MODEL, GIT_DIGEST_DEFAULT_TITLE).

    Args:
        config_path: Optional path to repos.yaml. If omitted, uses current dir or
            ~/.config/git-digest/repos.yaml.
        changes_only: If True, only show commits new since last run (persists state
            in cache dir).
        use_ai_summary: If True, use Ollama to generate a short AI digest instead of
            raw commit list.
        ollama_model: Ollama model name when use_ai_summary is True (default: from config or OLLAMA_MODEL).
        title: Report title (default: from config or GIT_DIGEST_DEFAULT_TITLE).

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
    state = load_state(config.cache_dir) if changes_only else {}

    summaries = []
    for repo_config in config.repos:
        last_sha = get_last_seen_sha(state, repo_config.url) if changes_only else None
        last_tag_names = (
            get_last_seen_tag_names(state, repo_config.url) if changes_only else None
        )
        summary = fetch_repo_summary(
            repo_config,
            config.cache_dir,
            last_seen_sha=last_sha,
            last_seen_tag_names=last_tag_names or None,
        )
        summaries.append(summary)
        if changes_only and not summary.error:
            entry = {}
            if summary.head_sha:
                entry["commit_sha"] = summary.head_sha
            if summary.recent_tag_names:
                entry["tag_names"] = summary.recent_tag_names
            if entry:
                state[repo_config.url] = entry

    if changes_only:
        save_state(config.cache_dir, state)

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
        report = format_report(summaries, title=report_title)

    return report


@mcp.tool()
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


def run() -> None:
    """Run the MCP server (stdio transport by default)."""
    mcp.run()


if __name__ == "__main__":
    run()
