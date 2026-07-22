"""Configuration loading for git-digest (YAML + optional .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

_REPO_FIELDS = {"url", "repo", "branch", "max_commits", "include_tags"}
_TOP_LEVEL_FIELDS = {
    "repos",
    "cache_dir",
    "max_commits",
    "default_title",
    "ollama_model",
    "ollama_url",
    "ollama_base_url",
    "ollama_timeout",
}


def _as_positive_int(value: Any, field_name: str) -> int:
    """Return a positive integer, rejecting YAML booleans and blank values."""
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer") from exc
    if result < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return result


def _as_bool(value: Any, field_name: str) -> bool:
    """Parse a boolean without treating arbitrary non-empty strings as true."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    raise ValueError(f"{field_name} must be true or false")


def _repo_identity(url: str) -> str:
    """Produce a stable identity for duplicate-repository detection."""
    normalized = url.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def _validate_repository_url(url: str) -> None:
    """Accept standard Git URLs while catching common configuration mistakes."""
    if any(character.isspace() for character in url):
        raise ValueError("Repository URL must not contain whitespace")
    if url.startswith(("./", "../", "/")):
        return
    if "@" in url and ":" in url and "://" not in url:
        return  # SCP-style SSH, for example git@github.com:owner/repo.git
    parsed = urlparse(url)
    if parsed.scheme and (parsed.netloc or parsed.scheme == "file"):
        return
    raise ValueError("Repository URL must be a Git URL, SSH URL, or local path")


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
        if not isinstance(data, dict):
            raise ValueError("Repository config must be a mapping")
        unknown_fields = set(data) - _REPO_FIELDS
        if unknown_fields:
            raise ValueError(f"Unknown repository option(s): {', '.join(sorted(unknown_fields))}")
        url = data.get("url") or data.get("repo")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Repository config must have 'url' or 'repo'")
        branch = data.get("branch", "HEAD")
        if not isinstance(branch, str) or not branch.strip():
            raise ValueError("branch must be a non-empty string")
        url = url.strip()
        _validate_repository_url(url)
        return cls(
            url=url,
            branch=branch.strip(),
            max_commits=_as_positive_int(data.get("max_commits", 10), "max_commits"),
            include_tags=_as_bool(data.get("include_tags", True), "include_tags"),
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
        if not isinstance(raw, dict):
            raise ValueError("Config file must contain a YAML mapping")
        unknown_fields = set(raw) - _TOP_LEVEL_FIELDS
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unknown configuration option(s): {names}")
        raw_repos = raw.get("repos", [])
        if not isinstance(raw_repos, list):
            raise ValueError("repos must be a YAML list")
        repos: list[RepoConfig] = []
        for item in raw_repos:
            if isinstance(item, str):
                repos.append(RepoConfig.from_dict({"url": item}))
            else:
                repos.append(RepoConfig.from_dict(item))
        cache = raw.get("cache_dir")
        if cache is not None and (not isinstance(cache, str) or not cache.strip()):
            raise ValueError("cache_dir must be a non-empty path")
        cache_path = Path(cache).expanduser() if cache else Path.home() / ".cache" / "git-digest"
        ollama_url = raw.get("ollama_url") or raw.get("ollama_base_url") or "http://127.0.0.1:11434"
        if not isinstance(ollama_url, str) or not ollama_url.strip():
            raise ValueError("ollama_url must be a non-empty URL")
        config = cls(
            repos=repos,
            cache_dir=cache_path,
            max_commits_default=_as_positive_int(raw.get("max_commits", 10), "max_commits"),
            default_title=str(raw.get("default_title", "Git updates summary")),
            ollama_model=str(raw.get("ollama_model", "gemma3n")),
            ollama_url=ollama_url.strip(),
            ollama_timeout=_as_positive_int(raw.get("ollama_timeout", 120), "ollama_timeout"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate the complete configuration before a network operation starts."""
        duplicates: set[str] = set()
        seen: set[str] = set()
        for repo in self.repos:
            identity = _repo_identity(repo.url)
            if identity in seen:
                duplicates.add(repo.url)
            seen.add(identity)
        if duplicates:
            raise ValueError(f"Duplicate repository URL(s): {', '.join(sorted(duplicates))}")
        _as_positive_int(self.max_commits_default, "max_commits")
        _as_positive_int(self.ollama_timeout, "ollama_timeout")

    def with_env_overrides(self) -> Config:
        """Return a new Config with env vars applied (env overrides YAML)."""
        cache = os.environ.get(ENV_CACHE_DIR)
        cache_path = Path(cache).expanduser().resolve() if cache else self.cache_dir
        config = Config(
            repos=self.repos,
            cache_dir=cache_path,
            max_commits_default=self.max_commits_default,
            default_title=(
                os.environ.get(ENV_DEFAULT_TITLE, self.default_title).strip() or self.default_title
            ),
            ollama_model=(
                os.environ.get(ENV_OLLAMA_MODEL, self.ollama_model).strip() or self.ollama_model
            ),
            ollama_url=(
                os.environ.get(ENV_OLLAMA_BASE_URL, self.ollama_url).strip() or self.ollama_url
            ),
            ollama_timeout=_as_positive_int(
                os.environ.get(ENV_OLLAMA_TIMEOUT, str(self.ollama_timeout)), "OLLAMA_TIMEOUT"
            ),
        )
        config.validate()
        return config

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
                    repos.append(RepoConfig.from_dict({"url": line}))
        config = cls(repos=repos)
        config.validate()
        return config
