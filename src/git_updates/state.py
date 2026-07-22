"""Persist last-seen commit and tag names per repo for --changes-only runs."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

STATE_FILENAME = "state.json"
LOCK_FILENAME = "state.lock"

# Value is either a legacy last-seen commit SHA or the current structured state.
StateValue = str | dict[str, Any]


@contextmanager
def state_lock(cache_dir: Path) -> Iterator[None]:
    """Serialize a load/update/save state transaction across concurrent cron runs.

    Callers should hold this lock around the whole read-modify-write transaction,
    rather than only around ``save_state``. On platforms without ``fcntl`` the
    context remains functional but cannot provide inter-process exclusion.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    lock_path = cache_dir / LOCK_FILENAME
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover - Windows fallback
            pass
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover - Windows fallback
                pass


def load_state(cache_dir: Path) -> dict[str, StateValue]:
    """
    Load state from cache_dir/state.json.

    Returns repo_url -> value where value is either:
    - str: legacy last_seen_commit_sha
    - dict: commit_sha plus optional tag_ids and newest_tag_date
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


def get_last_seen_tag_ids(state: dict[str, StateValue], repo_url: str) -> set[str] | None:
    """Return persisted ``name:target_sha`` tag identities, or None for legacy state.

    ``None`` is deliberately distinct from an empty set: an empty set means a
    previous run observed no tags, while ``None`` asks callers to use their legacy
    timestamp fallback exactly once.
    """
    val = state.get(repo_url)
    if not isinstance(val, dict) or "tag_ids" not in val:
        return None
    ids = val.get("tag_ids")
    if not isinstance(ids, list):
        return None
    return {tag_id for tag_id in ids if isinstance(tag_id, str)}


def get_last_seen_newest_tag_date(state: dict[str, StateValue], repo_url: str) -> str | None:
    """Return the newest tag's legacy timestamp, if one was persisted."""
    val = state.get(repo_url)
    if not isinstance(val, dict):
        return None
    date_val = val.get("newest_tag_date")
    return str(date_val) if isinstance(date_val, str) and date_val else None


def save_state(
    cache_dir: Path,
    state: dict[str, StateValue],
) -> None:
    """Atomically write state to cache_dir/state.json.

    Replacing a fully fsynced temporary file avoids exposing corrupt partial JSON if
    a scheduled run is interrupted while writing.
    """
    path = cache_dir / STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        # ``replace`` has already removed this path. This cleanup matters only if
        # serialization or fsync raises, and never touches the prior state file.
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
