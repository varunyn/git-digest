"""Persist last-seen commit and tag names per repo for --changes-only runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATE_FILENAME = "state.json"

# Value is either legacy str (last_seen_commit_sha) or dict with commit_sha + tag_names
StateValue = str | dict[str, Any]


def load_state(cache_dir: Path) -> dict[str, StateValue]:
    """
    Load state from cache_dir/state.json.

    Returns repo_url -> value where value is either:
    - str: legacy last_seen_commit_sha
    - dict: {"commit_sha": str, "tag_names": list[str], "newest_tag_date": str} (tag_names/newest_tag_date optional)
    """
    path = cache_dir / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_last_seen_sha(state: dict[str, StateValue], repo_url: str) -> str | None:
    """Return last-seen commit SHA for repo, or None. Handles legacy str and new dict format."""
    val = state.get(repo_url)
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return val.get("commit_sha")


def get_last_seen_tag_names(state: dict[str, StateValue], repo_url: str) -> set[str]:
    """Return set of last-seen tag names for repo. Empty if not stored (e.g. legacy state)."""
    val = state.get(repo_url)
    if not isinstance(val, dict):
        return set()
    names = val.get("tag_names")
    if not isinstance(names, list):
        return set()
    return set(n for n in names if isinstance(n, str))


def get_last_seen_newest_tag_date(state: dict[str, StateValue], repo_url: str) -> str | None:
    """Return ISO datetime of newest tag we've seen for repo, or None. Used to show only tags newer than last run."""
    val = state.get(repo_url)
    if not isinstance(val, dict):
        return None
    date_val = val.get("newest_tag_date")
    return str(date_val) if isinstance(date_val, str) and date_val else None


def save_state(
    cache_dir: Path,
    state: dict[str, StateValue],
) -> None:
    """Write state to cache_dir/state.json. Values may be str (legacy) or dict with commit_sha, tag_names, newest_tag_date."""
    path = cache_dir / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
