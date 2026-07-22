"""Regression tests for remote fetch and tag-change detection."""

from pathlib import Path

from git import Repo

from git_updates.config import RepoConfig
from git_updates.fetcher import _safe_dir_name, fetch_repo_summary


def _commit(repo: Repo, path: Path, contents: str, message: str) -> str:
    path.write_text(contents, encoding="utf-8")
    repo.index.add([path.name])
    return repo.index.commit(message).hexsha


def test_cache_directory_includes_url_hash() -> None:
    """URLs sharing an owner/repository suffix cannot share a cache checkout."""
    assert _safe_dir_name("https://github.com/acme/widgets.git") != _safe_dir_name(
        "https://git.example.com/acme/widgets.git"
    )


def test_fetch_uses_updated_configured_remote_branch(tmp_path: Path) -> None:
    """A fetch reports a new commit on the configured branch, not stale local HEAD."""
    source_path = tmp_path / "source"
    source = Repo.init(source_path, initial_branch="stable")
    tracked = source_path / "tracked.txt"
    _commit(source, tracked, "one", "first")
    config = RepoConfig(url=str(source_path), branch="stable")

    first = fetch_repo_summary(config, tmp_path / "cache")
    assert first.error is None
    _commit(source, tracked, "two", "second")

    second = fetch_repo_summary(config, tmp_path / "cache", last_seen_sha=first.head_sha)
    assert second.error is None
    assert [commit.subject for commit in second.commits] == ["second"]


def test_identity_detects_tag_created_on_an_old_commit(tmp_path: Path) -> None:
    """Tag changes use name+target identity rather than the tagged commit timestamp."""
    source_path = tmp_path / "source"
    source = Repo.init(source_path, initial_branch="main")
    tracked = source_path / "tracked.txt"
    old_sha = _commit(source, tracked, "one", "first")
    source.create_tag("v1", ref=old_sha)
    _commit(source, tracked, "two", "second")
    config = RepoConfig(url=str(source_path), branch="main")

    first = fetch_repo_summary(config, tmp_path / "cache")
    assert first.error is None
    assert first.tag_ids
    source.create_tag("v2", ref=old_sha)

    second = fetch_repo_summary(
        config,
        tmp_path / "cache",
        last_seen_sha=first.head_sha,
        last_seen_tag_ids=set(first.tag_ids),
    )
    assert second.error is None
    assert [tag.name for tag in second.tags] == ["v2"]


def test_changes_only_marks_results_truncated_at_commit_limit(tmp_path: Path) -> None:
    """Callers can preserve state when a report cannot include every new commit."""
    source_path = tmp_path / "source"
    source = Repo.init(source_path, initial_branch="main")
    tracked = source_path / "tracked.txt"
    _commit(source, tracked, "one", "first")
    config = RepoConfig(url=str(source_path), branch="main", max_commits=1)
    first = fetch_repo_summary(config, tmp_path / "cache")
    _commit(source, tracked, "two", "second")
    _commit(source, tracked, "three", "third")

    summary = fetch_repo_summary(config, tmp_path / "cache", last_seen_sha=first.head_sha)

    assert summary.error is None
    assert summary.commits_truncated is True
    assert [commit.subject for commit in summary.commits] == ["third"]
