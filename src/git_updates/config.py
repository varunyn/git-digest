"""Configuration loading for git-digest (YAML + optional .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Default config file search order (used by CLI and MCP).
DEFAULT_CONFIG_PATHS: list[Path] = [
    Path.cwd() / "repos.yaml",
    Path.cwd() / "repos.yml",
    Path.home() / ".config" / "git-digest" / "repos.yaml",
]

# Default .env search order (optional; env vars override YAML).
DEFAULT_DOTENV_PATHS: list[Path] = [
    Path.cwd() / ".env",
    Path.home() / ".config" / "git-digest" / ".env",
]

# Env var names for overrides.
ENV_OLLAMA_BASE_URL = "OLLAMA_BASE_URL"
ENV_OLLAMA_MODEL = "OLLAMA_MODEL"
ENV_OLLAMA_TIMEOUT = "OLLAMA_TIMEOUT"
ENV_CACHE_DIR = "GIT_DIGEST_CACHE_DIR"
ENV_DEFAULT_TITLE = "GIT_DIGEST_DEFAULT_TITLE"


def load_dotenv_for_app() -> None:
    """Load .env from first existing path in DEFAULT_DOTENV_PATHS (no override of existing env)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for p in DEFAULT_DOTENV_PATHS:
        if p.exists():
            load_dotenv(p, override=False)
            break


@dataclass
class RepoConfig:
    """Configuration for a single repository."""

    url: str
    branch: str = "HEAD"
    max_commits: int = 10
    include_tags: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepoConfig:
        """Build RepoConfig from a dict (e.g. from YAML)."""
        url = data.get("url") or data.get("repo")
        if not url:
            raise ValueError("Repository config must have 'url' or 'repo'")
        return cls(
            url=str(url).strip(),
            branch=str(data.get("branch", "HEAD")).strip(),
            max_commits=int(data.get("max_commits", 10)),
            include_tags=bool(data.get("include_tags", True)),
        )


@dataclass
class Config:
    """Top-level configuration (repos + app defaults from YAML; env can override)."""

    repos: list[RepoConfig] = field(default_factory=list)
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "git-digest")
    max_commits_default: int = 10
    # Optional app defaults (report title, Ollama); overridable by env and CLI/MCP.
    default_title: str = "Git updates summary"
    ollama_model: str = "gemma3n"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_timeout: int = 120

    @classmethod
    def from_yaml(cls, path: Path) -> Config:
        """Load config from a YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        raw = yaml.safe_load(path.read_text()) or {}
        repos: list[RepoConfig] = []
        for item in raw.get("repos", []):
            if isinstance(item, str):
                repos.append(RepoConfig(url=item.strip()))
            else:
                repos.append(RepoConfig.from_dict(item))
        cache = raw.get("cache_dir")
        cache_path = Path(cache).expanduser() if cache else Path.home() / ".cache" / "git-digest"
        ollama_url = raw.get("ollama_url") or raw.get("ollama_base_url") or "http://127.0.0.1:11434"
        ollama_url = str(ollama_url).strip()
        return cls(
            repos=repos,
            cache_dir=cache_path,
            max_commits_default=int(raw.get("max_commits", 10)),
            default_title=str(raw.get("default_title", "Git updates summary")),
            ollama_model=str(raw.get("ollama_model", "gemma3n")),
            ollama_url=ollama_url.strip(),
            ollama_timeout=int(raw.get("ollama_timeout", 120)),
        )

    def with_env_overrides(self) -> Config:
        """Return a new Config with env vars applied (env overrides YAML)."""
        cache = os.environ.get(ENV_CACHE_DIR)
        cache_path = Path(cache).expanduser().resolve() if cache else self.cache_dir
        return Config(
            repos=self.repos,
            cache_dir=cache_path,
            max_commits_default=self.max_commits_default,
            default_title=os.environ.get(ENV_DEFAULT_TITLE, self.default_title).strip() or self.default_title,
            ollama_model=os.environ.get(ENV_OLLAMA_MODEL, self.ollama_model).strip() or self.ollama_model,
            ollama_url=os.environ.get(ENV_OLLAMA_BASE_URL, self.ollama_url).strip() or self.ollama_url,
            ollama_timeout=int(os.environ.get(ENV_OLLAMA_TIMEOUT, str(self.ollama_timeout))) or self.ollama_timeout,
        )

    @classmethod
    def from_repo_list(cls, paths: list[Path]) -> Config:
        """Load repos from plain text files (one URL per line)."""
        repos: list[RepoConfig] = []
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    repos.append(RepoConfig(url=line))
        return cls(repos=repos)
