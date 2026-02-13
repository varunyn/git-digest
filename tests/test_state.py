"""Tests for state persistence."""

from pathlib import Path

import pytest

from git_updates.state import (
    STATE_FILENAME,
    get_last_seen_sha,
    get_last_seen_tag_names,
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


def test_save_and_load_state_with_tags(tmp_path: Path) -> None:
    """State with commit_sha and tag_names round-trips correctly."""
    state = {
        "https://github.com/a/b": {
            "commit_sha": "abc123",
            "tag_names": ["v1.0", "v0.9"],
        },
    }
    save_state(tmp_path, state)
    loaded = load_state(tmp_path)
    assert loaded == state


def test_get_last_seen_sha_legacy(tmp_path: Path) -> None:
    """get_last_seen_sha returns value for legacy string state."""
    state = {"https://github.com/a/b": "abc123"}
    assert get_last_seen_sha(state, "https://github.com/a/b") == "abc123"
    assert get_last_seen_sha(state, "https://other.com/x") is None


def test_get_last_seen_sha_dict(tmp_path: Path) -> None:
    """get_last_seen_sha returns commit_sha for dict state."""
    state = {"https://github.com/a/b": {"commit_sha": "def456", "tag_names": ["v1"]}}
    assert get_last_seen_sha(state, "https://github.com/a/b") == "def456"


def test_get_last_seen_tag_names_empty_or_legacy(tmp_path: Path) -> None:
    """get_last_seen_tag_names returns empty set for missing or legacy state."""
    state = {"https://github.com/a/b": "abc123"}
    assert get_last_seen_tag_names(state, "https://github.com/a/b") == set()
    assert get_last_seen_tag_names(state, "https://other.com/x") == set()


def test_get_last_seen_tag_names_dict(tmp_path: Path) -> None:
    """get_last_seen_tag_names returns tag list from dict state."""
    state = {
        "https://github.com/a/b": {"commit_sha": "abc", "tag_names": ["v1.0", "v0.9"]},
    }
    assert get_last_seen_tag_names(state, "https://github.com/a/b") == {"v1.0", "v0.9"}


def test_load_state_invalid_json_returns_empty(tmp_path: Path) -> None:
    """Invalid JSON in state file returns empty dict."""
    (tmp_path / STATE_FILENAME).write_text("not json")
    assert load_state(tmp_path) == {}
