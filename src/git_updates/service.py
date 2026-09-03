"""Shared fetch + changes-only state service for CLI and MCP."""

from __future__ import annotations

import logging
from pathlib import Path

from git_updates.config import Config
from git_updates.fetcher import RepoSummary, fetch_repo_summary
from git_updates.state import (
    get_last_seen_newest_tag_date,
    get_last_seen_sha,
    get_last_seen_tag_ids,
    load_state,
    save_state,
    state_lock,
)

logger = logging.getLogger("git_updates.service")


def validate_config_file(config_path: Path | None) -> tuple[bool, str]:
    """Validate a config file without fetching any repository.

    Returns (True, "OK: N repos") on success, else (False, "Error: ...").
    """
    from git_updates.config import DEFAULT_CONFIG_PATHS, Config

    try:
        if config_path is not None:
            config = Config.from_yaml(config_path).with_env_overrides()
        else:
            config = None
            for p in DEFAULT_CONFIG_PATHS:
                if p.exists():
                    config = Config.from_yaml(p).with_env_overrides()
                    break
            if config is None:
                paths = ", ".join(str(p) for p in DEFAULT_CONFIG_PATHS)
                return (False, f"Error: no config found. Create one of: {paths}")
        config.validate()
    except Exception as e:
        return (False, f"Error: {e}")
    count = len(config.repos)
    noun = "repo" if count == 1 else "repos"
    return (True, f"OK: {count} {noun}")


def collect_updates(
    config: Config, *, changes_only: bool, verbose: bool = False
) -> list[RepoSummary]:
    """Fetch all repos; when changes_only, wrap in state_lock load/save transaction."""

    def _collect(state: dict) -> list[RepoSummary]:
        summaries: list[RepoSummary] = []
        for repo_config in config.repos:
            if verbose:
                logger.info("Fetching %s ...", repo_config.url)
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
                entry: dict = {}
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
            summaries = _collect(state)
            save_state(config.cache_dir, state)
            return summaries
    return _collect({})
