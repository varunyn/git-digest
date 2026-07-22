"""Tests for state persistence."""

from pathlib import Path

from git_updates.state import (
    STATE_FILENAME,
    get_last_seen_newest_tag_date,
    get_last_seen_sha,
    get_last_seen_tag_ids,
    load_state,
    save_state,
)


def test_load_state_missing_returns_empty(tmp_path: Path) -> None:
    """Missing state file returns empty dict."""
    assert load_state(tmp_path) == {}


def test_save_and_load_state_legacy(tmp_path: Path) -> None:
    """Legacy state (url -> sha string) round-trips correctly."""
    state = {"https://github.com/a/b": "abc123", "https://gitlab.com/x/y": "def456"}
    save_state(tmp_path, state)
    assert (tmp_path / STATE_FILENAME).exists()
    assert load_state(tmp_path) == state


def test_get_last_seen_sha_legacy(tmp_path: Path) -> None:
    """get_last_seen_sha returns value for legacy string state."""
    state = {"https://github.com/a/b": "abc123"}
    assert get_last_seen_sha(state, "https://github.com/a/b") == "abc123"
    assert get_last_seen_sha(state, "https://other.com/x") is None


def test_get_last_seen_sha_dict(tmp_path: Path) -> None:
    """get_last_seen_sha returns commit_sha for dict state."""
    state = {"https://github.com/a/b": {"commit_sha": "def456", "tag_ids": ["v1:def456"]}}
    assert get_last_seen_sha(state, "https://github.com/a/b") == "def456"


def test_get_last_seen_tag_ids_distinguishes_legacy_from_empty() -> None:
    """Identity state preserves the difference between unknown and no tags."""
    assert get_last_seen_tag_ids({}, "https://github.com/a/b") is None
    state = {"https://github.com/a/b": {"tag_ids": []}}
    assert get_last_seen_tag_ids(state, "https://github.com/a/b") == set()
    state["https://github.com/a/b"] = {"tag_ids": ["v1:abc", 1]}
    assert get_last_seen_tag_ids(state, "https://github.com/a/b") == {"v1:abc"}


def test_get_last_seen_newest_tag_date_none(tmp_path: Path) -> None:
    """get_last_seen_newest_tag_date returns None for missing or legacy state."""
    state = {"https://github.com/a/b": "abc123"}
    assert get_last_seen_newest_tag_date(state, "https://github.com/a/b") is None
    assert get_last_seen_newest_tag_date(state, "https://other.com/x") is None


def test_get_last_seen_newest_tag_date_dict(tmp_path: Path) -> None:
    """get_last_seen_newest_tag_date returns value from dict state."""
    state = {
        "https://github.com/a/b": {
            "commit_sha": "abc",
            "newest_tag_date": "2025-02-01 12:00:00",
        },
    }
    assert get_last_seen_newest_tag_date(state, "https://github.com/a/b") == "2025-02-01 12:00:00"


def test_save_and_load_state_with_newest_tag_date(tmp_path: Path) -> None:
    """State with commit_sha and newest_tag_date round-trips correctly."""
    state = {
        "https://github.com/a/b": {
            "commit_sha": "abc123",
            "newest_tag_date": "2025-02-10 08:00:00",
        },
    }
    save_state(tmp_path, state)
    assert load_state(tmp_path) == state


def test_load_state_invalid_json_returns_empty(tmp_path: Path) -> None:
    """Invalid JSON in state file returns empty dict."""
    (tmp_path / STATE_FILENAME).write_text("not json")
    assert load_state(tmp_path) == {}
