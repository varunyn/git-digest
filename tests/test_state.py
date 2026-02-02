"""Tests for state persistence."""

from pathlib import Path

import pytest

from git_updates.state import load_state, save_state, STATE_FILENAME


def test_load_state_missing_returns_empty(tmp_path: Path) -> None:
    """Missing state file returns empty dict."""
    assert load_state(tmp_path) == {}


def test_save_and_load_state(tmp_path: Path) -> None:
    """State round-trips correctly."""
    state = {"https://github.com/a/b": "abc123", "https://gitlab.com/x/y": "def456"}
    save_state(tmp_path, state)
    assert (tmp_path / STATE_FILENAME).exists()
    assert load_state(tmp_path) == state


def test_load_state_invalid_json_returns_empty(tmp_path: Path) -> None:
    """Invalid JSON in state file returns empty dict."""
    (tmp_path / STATE_FILENAME).write_text("not json")
    assert load_state(tmp_path) == {}
