"""Persist last-seen commit per repo for --changes-only runs."""

from __future__ import annotations

import json
from pathlib import Path

STATE_FILENAME = "state.json"


def load_state(cache_dir: Path) -> dict[str, str]:
    """Load state from cache_dir/state.json. Returns repo_url -> last_seen_commit_sha."""
    path = cache_dir / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(cache_dir: Path, state: dict[str, str]) -> None:
    """Write state to cache_dir/state.json."""
    path = cache_dir / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
