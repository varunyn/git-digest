"""Helpers for creating a safe starter git-digest configuration."""

from __future__ import annotations

from pathlib import Path

STARTER_CONFIG = """\
# git-digest configuration
# Add one or more repository URLs below. Do not put access tokens in this file.

# cache_dir: ~/.cache/git-digest
# max_commits: 10
# default_title: My git digest

repos:
  - https://github.com/owner/repository.git
    # branch: main
    # max_commits: 10
    # include_tags: true
"""


def initialize_config(path: Path, *, overwrite: bool = False) -> Path:
    """Create a commented starter config and return its resolved path.

    Existing configuration is never overwritten unless the caller opts in.
    """
    path = path.expanduser()
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing configuration: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STARTER_CONFIG, encoding="utf-8")
    return path.resolve()
