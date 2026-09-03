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


def test_doctor_ok(tmp_path: Path, monkeypatch, capsys) -> None:
    good = tmp_path / "good.yaml"
    good.write_text("repos:\n  - https://github.com/o/r.git\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["git-digest", "--doctor", "--config", str(good), "--cache-dir", str(tmp_path / "cache")],
    )
    assert main() in (0, 1)  # 1 allowed if git/ollama missing in CI
    out = capsys.readouterr().out
    assert "PASS" in out or "FAIL" in out or "WARN" in out  # exits without traceback


def test_doctor_missing_config_reports_failure_and_continues(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "git-digest",
            "--doctor",
            "--config",
            str(tmp_path / "missing.yaml"),
            "--cache-dir",
            str(cache_dir),
        ],
    )

    assert main() == 1
    out = capsys.readouterr().out
    assert "FAIL: config -" in out
    assert "cache_dir" in out


def test_doctor_invalid_config_reports_failure_and_continues(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("repos:\n  - {}\n", encoding="utf-8")
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(
        sys,
        "argv",
        ["git-digest", "--doctor", "--config", str(config_path), "--cache-dir", str(cache_dir)],
    )

    assert main() == 1
    out = capsys.readouterr().out
    assert "FAIL: config -" in out
    assert "cache_dir" in out
