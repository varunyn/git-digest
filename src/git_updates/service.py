"""Shared fetch + changes-only state service for CLI and MCP."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from git_updates.config import Config
from git_updates.fetcher import RepoSummary, fetch_repo_summary
from git_updates.state import (
    STATE_FILENAME,
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


def doctor_report(config: Config) -> list[tuple[str, bool | None, str]]:
    """Run read-only environment checks (no remote fetch).

    Returns (check, ok, detail) per check where ok None means WARN.
    Ollama problems are WARN, never FAIL.
    """
    results: list[tuple[str, bool | None, str]] = []

    try:
        config.validate()
    except Exception as e:
        results.append(("config", False, f"invalid: {e}"))
    else:
        count = len(config.repos)
        noun = "repo" if count == 1 else "repos"
        results.append(("config", True, f"{count} {noun} configured"))

    try:
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        probe = config.cache_dir / ".doctor-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        results.append(("cache_dir", True, f"writable: {config.cache_dir}"))
    except Exception as e:
        results.append(("cache_dir", False, f"not writable: {e}"))

    git = shutil.which("git")
    if git is None:
        results.append(("git", False, "git not found on PATH"))
    else:
        try:
            proc = subprocess.run([git, "--version"], capture_output=True, text=True, timeout=10)
        except Exception as e:
            results.append(("git", False, f"git check failed: {e}"))
        else:
            version = proc.stdout.strip() or proc.stderr.strip()
            if proc.returncode != 0:
                results.append(("git", False, "git --version failed"))
            else:
                results.append(("git", True, version or "git found"))

    try:
        state_path = config.cache_dir / STATE_FILENAME
        if not state_path.exists():
            load_state(config.cache_dir)
            results.append(("state", True, "no state yet (first run)"))
        else:
            try:
                json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
                results.append(("state", None, f"state.json corrupt, will reset: {e}"))
            else:
                load_state(config.cache_dir)
                results.append(("state", True, f"state.json OK: {state_path}"))
    except Exception as e:
        results.append(("state", None, f"state check inconclusive: {e}"))

    try:
        from git_updates.ollama_client import list_models

        models = list_models(config.ollama_url)
    except Exception as e:
        results.append(("ollama", None, f"unreachable ({e})"))
    else:
        wanted = config.ollama_model
        if not models:
            results.append(("ollama", None, f"unreachable or no models at {config.ollama_url}"))
        elif wanted in models or any(m.split(":")[0] == wanted for m in models):
            results.append(("ollama", True, f"model '{wanted}' available"))
        else:
            results.append(
                ("ollama", None, f"model '{wanted}' not in {len(models)} installed model(s)")
            )
    return results


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
