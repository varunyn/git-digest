"""Tests for config loading."""

import os
from pathlib import Path

import pytest

from git_updates.config import (
    ENV_DEFAULT_TITLE,
    ENV_OLLAMA_MODEL,
    Config,
    RepoConfig,
)
from git_updates.initializer import STARTER_CONFIG, initialize_config


def test_repo_config_from_dict_simple() -> None:
    """URL-only dict produces RepoConfig with defaults."""
    c = RepoConfig.from_dict({"url": "https://github.com/foo/bar.git"})
    assert c.url == "https://github.com/foo/bar.git"
    assert c.branch == "HEAD"
    assert c.max_commits == 10
    assert c.include_tags is True


def test_repo_config_from_dict_full() -> None:
    """Full dict overrides defaults."""
    c = RepoConfig.from_dict(
        {
            "url": "https://gitlab.com/a/b.git",
            "branch": "develop",
            "max_commits": 5,
            "include_tags": False,
        }
    )
    assert c.url == "https://gitlab.com/a/b.git"
    assert c.branch == "develop"
    assert c.max_commits == 5
    assert c.include_tags is False


def test_repo_config_accepts_repo_key() -> None:
    """'repo' key is accepted as alias for 'url'."""
    c = RepoConfig.from_dict({"repo": "https://github.com/x/y"})
    assert c.url == "https://github.com/x/y"


def test_repo_config_missing_url_raises() -> None:
    """Missing url/repo raises ValueError."""
    with pytest.raises(ValueError, match="url.*repo"):
        RepoConfig.from_dict({})


def test_config_from_yaml(tmp_path: Path) -> None:
    """YAML with repos list loads correctly."""
    yaml_path = tmp_path / "repos.yaml"
    yaml_path.write_text("""
repos:
  - https://github.com/a/b.git
  - url: https://github.com/c/d.git
    branch: main
    max_commits: 3
cache_dir: /tmp/my-cache
max_commits: 7
""")
    config = Config.from_yaml(yaml_path)
    assert len(config.repos) == 2
    assert config.repos[0].url == "https://github.com/a/b.git"
    assert config.repos[1].branch == "main"
    assert config.repos[1].max_commits == 3
    assert config.cache_dir == Path("/tmp/my-cache")
    assert config.default_title == "Git updates summary"
    assert config.ollama_model == "gemma3n"
    assert config.ollama_url == "http://127.0.0.1:11434"
    assert config.ollama_timeout == 120


def test_config_from_yaml_with_ollama_and_title(tmp_path: Path) -> None:
    """YAML with ollama_* and default_title loads correctly."""
    yaml_path = tmp_path / "repos.yaml"
    yaml_path.write_text("""
repos:
  - https://github.com/a/b.git
default_title: My digest
ollama_model: mistral
ollama_url: http://localhost:11434
ollama_timeout: 60
""")
    config = Config.from_yaml(yaml_path)
    assert config.default_title == "My digest"
    assert config.ollama_model == "mistral"
    assert config.ollama_url == "http://localhost:11434"
    assert config.ollama_timeout == 60


def test_config_with_env_overrides(tmp_path: Path) -> None:
    """with_env_overrides() applies env vars over YAML."""
    yaml_path = tmp_path / "repos.yaml"
    yaml_path.write_text("""
repos:
  - https://github.com/a/b.git
default_title: From YAML
ollama_model: gemma3n
""")
    config = Config.from_yaml(yaml_path)
    assert config.default_title == "From YAML"
    assert config.ollama_model == "gemma3n"
    prev_title = os.environ.get(ENV_DEFAULT_TITLE)
    prev_model = os.environ.get(ENV_OLLAMA_MODEL)
    try:
        os.environ[ENV_DEFAULT_TITLE] = "From env"
        os.environ[ENV_OLLAMA_MODEL] = "llama3"
        overridden = config.with_env_overrides()
        assert overridden.default_title == "From env"
        assert overridden.ollama_model == "llama3"
    finally:
        if prev_title is not None:
            os.environ[ENV_DEFAULT_TITLE] = prev_title
        elif ENV_DEFAULT_TITLE in os.environ:
            del os.environ[ENV_DEFAULT_TITLE]
        if prev_model is not None:
            os.environ[ENV_OLLAMA_MODEL] = prev_model
        elif ENV_OLLAMA_MODEL in os.environ:
            del os.environ[ENV_OLLAMA_MODEL]


def test_config_from_repo_list(tmp_path: Path) -> None:
    """Plain text file with one URL per line loads correctly."""
    f = tmp_path / "repos.txt"
    f.write_text("https://github.com/foo/bar.git\n# comment\n\nhttps://gitlab.com/x/y.git\n")
    config = Config.from_repo_list([f])
    assert len(config.repos) == 2
    assert config.repos[0].url == "https://github.com/foo/bar.git"
    assert config.repos[1].url == "https://gitlab.com/x/y.git"


@pytest.mark.parametrize(
    ("yaml", "error"),
    [
        ("repos: not-a-list", "repos must be a YAML list"),
        ("repos:\n  - url: https://github.com/a/b\n    max_commits: 0", "max_commits"),
        ("repos:\n  - url: https://github.com/a/b\n    include_tags: sometimes", "include_tags"),
        ("repos:\n  - url: not a URL", "Repository URL"),
        ("repos:\n  - url: https://github.com/a/b\nunknown_key: true", "Unknown configuration"),
    ],
)
def test_config_rejects_invalid_values(tmp_path: Path, yaml: str, error: str) -> None:
    """Invalid config values fail with a useful error before git is invoked."""
    path = tmp_path / "repos.yaml"
    path.write_text(yaml)
    with pytest.raises(ValueError, match=error):
        Config.from_yaml(path)


def test_config_rejects_duplicate_normalized_repository_urls(tmp_path: Path) -> None:
    """A remote cannot be listed twice with superficial URL differences."""
    path = tmp_path / "repos.yaml"
    path.write_text("repos:\n  - https://github.com/a/b.git\n  - https://github.com/a/b/\n")
    with pytest.raises(ValueError, match="Duplicate repository"):
        Config.from_yaml(path)


def test_initialize_config_creates_starter_without_overwriting(tmp_path: Path) -> None:
    """The reusable initializer writes a safe starter config exactly once."""
    path = tmp_path / "nested" / "repos.yaml"
    result = initialize_config(path)
    assert result == path.resolve()
    assert path.read_text() == STARTER_CONFIG
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        initialize_config(path)


def test_initialize_config_can_explicitly_overwrite(tmp_path: Path) -> None:
    """Overwrite requires an explicit caller choice."""
    path = tmp_path / "repos.yaml"
    path.write_text("old config")
    initialize_config(path, overwrite=True)
    assert path.read_text() == STARTER_CONFIG


def test_top_level_max_commits_applies_to_plain_urls(tmp_path):
    p = tmp_path / "repos.yaml"
    p.write_text("max_commits: 5\nrepos:\n  - https://github.com/o/r.git\n", encoding="utf-8")
    from git_updates.config import Config

    cfg = Config.from_yaml(p)
    assert cfg.max_commits_default == 5
    assert cfg.repos[0].max_commits == 5


def test_explicit_per_repo_wins(tmp_path):
    p = tmp_path / "repos.yaml"
    p.write_text(
        "max_commits: 5\nrepos:\n  - url: https://github.com/o/r.git\n    max_commits: 3\n",
        encoding="utf-8",
    )
    from git_updates.config import Config

    cfg = Config.from_yaml(p)
    assert cfg.repos[0].max_commits == 3
