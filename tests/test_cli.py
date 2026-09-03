"""Tests for CLI-only workflow additions."""

from __future__ import annotations

import sys
from pathlib import Path

from git_updates.cli import main


def test_init_creates_starter_config(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "repos.yaml"
    monkeypatch.setattr(sys, "argv", ["git-digest", "--init", str(config_path)])

    assert main() == 0
    assert "Created starter configuration" in capsys.readouterr().out
    assert "repos:" in config_path.read_text(encoding="utf-8")


def test_init_refuses_existing_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "repos.yaml"
    config_path.write_text("repos: []\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["git-digest", "--init", str(config_path)])

    assert main() == 2


def test_validate_ok_and_bad(tmp_path: Path, monkeypatch, capsys) -> None:
    import sys

    from git_updates.cli import main

    good = tmp_path / "good.yaml"
    good.write_text("repos:\n  - https://github.com/o/r.git\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["git-digest", "--validate", "--config", str(good)])
    assert main() == 0
    assert "OK" in capsys.readouterr().out
    bad = tmp_path / "bad.yaml"
    bad.write_text("repos:\n  - {}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["git-digest", "--validate", "--config", str(bad)])
    assert main() == 2
