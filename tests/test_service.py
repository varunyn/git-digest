# tests/test_service.py
from pathlib import Path

from git import Repo

from git_updates.config import Config, RepoConfig
from git_updates.service import collect_updates


def _commit(repo: Repo, path: Path, contents: str, message: str) -> str:
    path.write_text(contents, encoding="utf-8")
    repo.index.add([path.name])
    return repo.index.commit(message).hexsha


def test_collect_updates_basic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    repo = Repo.init(source, initial_branch="main")
    tracked = source / "tracked.txt"
    _commit(repo, tracked, "one", "first")
    cfg = Config(repos=[RepoConfig(url=str(source), branch="main")], cache_dir=tmp_path / "cache")
    summaries = collect_updates(cfg, changes_only=False)
    assert len(summaries) == 1
    assert summaries[0].error is None
    assert [c.subject for c in summaries[0].commits] == ["first"]


def test_collect_updates_changes_only_advances_state(tmp_path: Path) -> None:
    source = tmp_path / "source"
    repo = Repo.init(source, initial_branch="main")
    tracked = source / "tracked.txt"
    _commit(repo, tracked, "one", "first")
    cfg = Config(repos=[RepoConfig(url=str(source), branch="main")], cache_dir=tmp_path / "cache")
    first = collect_updates(cfg, changes_only=True)
    assert first[0].head_sha is not None
    _commit(repo, tracked, "two", "second")
    second = collect_updates(cfg, changes_only=True)
    assert [c.subject for c in second[0].commits] == ["second"]


def test_cli_and_service_share_truncation_guard(tmp_path: Path) -> None:
    # Verifies service preserves cli.py:242 guard: truncated reports do not advance state.
    from git_updates.state import load_state

    source = tmp_path / "src2"
    repo = Repo.init(source, initial_branch="main")
    tracked = source / "t.txt"
    _commit(repo, tracked, "one", "first")
    cfg = Config(
        repos=[RepoConfig(url=str(source), branch="main", max_commits=1)],
        cache_dir=tmp_path / "cache2",
    )
    first = collect_updates(cfg, changes_only=True)
    assert first[0].head_sha is not None
    _commit(repo, tracked, "two", "second")
    _commit(repo, tracked, "three", "third")
    second = collect_updates(cfg, changes_only=True)
    assert second[0].commits_truncated is True
    state = load_state(cfg.cache_dir)
    # state must still point at first head, not truncated head
    assert state[str(source)]["commit_sha"] == first[0].head_sha
