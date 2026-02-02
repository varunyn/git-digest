"""Fetch repo data (commits and tags) from git remotes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from git import Repo
from git.exc import GitCommandError

from git_updates.config import RepoConfig

if TYPE_CHECKING:
    from git import Commit
    from git import TagReference


@dataclass
class CommitInfo:
    """Summary of a single commit."""

    sha_short: str
    author: str
    date_iso: str
    subject: str
    refs: str = ""


@dataclass
class TagInfo:
    """Summary of a tag (release)."""

    name: str
    sha_short: str
    date_iso: str
    message: str = ""


@dataclass
class RepoSummary:
    """Summary of updates for one repository."""

    url: str
    name: str
    branch: str
    commits: list[CommitInfo] = field(default_factory=list)
    tags: list[TagInfo] = field(default_factory=list)
    error: str | None = None
    since_last_run: bool = False
    head_sha: str | None = None

    @property
    def display_name(self) -> str:
        """Human-readable repo name (e.g. owner/repo from URL)."""
        return self.name or self.url


def _repo_name_from_url(url: str) -> str:
    """Derive a short name from repo URL (e.g. owner/repo)."""
    url = url.rstrip("/")
    # Strip .git
    if url.lower().endswith(".git"):
        url = url[:-4]
    # Take last two path parts (owner/repo)
    parts = [p for p in url.replace("\\", "/").split("/") if p]
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return parts[-1] if parts else url


def _safe_dir_name(url: str) -> str:
    """Safe directory name for caching (no slashes or colons)."""
    name = _repo_name_from_url(url).replace("/", "_").replace(":", "_")
    return re.sub(r"[^\w.-]", "_", name)


def _ensure_cloned(cache_dir: Path, config: RepoConfig) -> Path:
    """Ensure repo is cloned in cache_dir; return path to repo."""
    repo_dir = cache_dir / _safe_dir_name(config.url)
    if repo_dir.exists() and (repo_dir / ".git").exists():
        return repo_dir
    repo_dir.mkdir(parents=True, exist_ok=True)
    Repo.clone_from(
        config.url,
        repo_dir,
        depth=100,
        single_branch=True,
        branch=config.branch if config.branch != "HEAD" else None,
    )
    return repo_dir


def _commits_to_infos(commits: list[Commit], max_n: int) -> list[CommitInfo]:
    """Convert GitPython commits to CommitInfo list."""
    result: list[CommitInfo] = []
    for c in commits[:max_n]:
        refs = ""
        ref_list = getattr(c, "references", None)
        if ref_list:
            refs = " ".join(getattr(r, "name", str(r)) for r in ref_list)
        result.append(
            CommitInfo(
                sha_short=c.hexsha[:7],
                author=c.author.name or "",
                date_iso=c.committed_datetime.strftime("%Y-%m-%d %H:%M") if c.committed_datetime else "",
                subject=(c.message or "").split("\n")[0].strip()[:80],
                refs=refs,
            )
        )
    return result


def _tags_to_infos(repo: Repo, max_tags: int = 10) -> list[TagInfo]:
    """Get recent tags with commit date and message."""
    result: list[TagInfo] = []
    try:
        tags = sorted(repo.tags, key=lambda t: t.commit.committed_datetime or 0, reverse=True)
    except Exception:
        return result
    for tag in tags[:max_tags]:
        try:
            commit = tag.commit
            date_str = (
                commit.committed_datetime.strftime("%Y-%m-%d %H:%M")
                if commit.committed_datetime
                else ""
            )
            msg = ""
            if tag.tag is not None and tag.tag.message:
                msg = (tag.tag.message or "").split("\n")[0].strip()[:60]
            result.append(
                TagInfo(
                    name=tag.name,
                    sha_short=commit.hexsha[:7],
                    date_iso=date_str,
                    message=msg,
                )
            )
        except Exception:
            continue
    return result


def _commits_since_sha(
    repo: Repo,
    target: object,
    last_seen_sha: str,
    max_count: int,
) -> list:
    """Return commits from target back until we hit last_seen_sha (exclusive)."""
    from git import Commit

    new_commits: list[Commit] = []
    for c in repo.iter_commits(target, max_count=max_count * 2):
        if c.hexsha == last_seen_sha or c.hexsha.startswith(last_seen_sha):
            break
        new_commits.append(c)
        if len(new_commits) >= max_count:
            break
    return new_commits


def fetch_repo_summary(
    config: RepoConfig,
    cache_dir: Path,
    last_seen_sha: str | None = None,
) -> RepoSummary:
    """
    Fetch latest commits and optional tags for one repo.

    Clones to cache_dir if needed (shallow), then fetches and builds summary.
    If last_seen_sha is set, only commits newer than that are included (for --changes-only).
    """
    name = _repo_name_from_url(config.url)
    summary = RepoSummary(url=config.url, name=name, branch=config.branch)

    try:
        repo_path = _ensure_cloned(cache_dir, config)
        repo = Repo(repo_path)
        origin = repo.remotes.origin
        origin.fetch()
        target = repo.head
        if config.branch != "HEAD":
            if config.branch in repo.heads:
                target = repo.heads[config.branch]
            else:
                for ref in origin.refs:
                    if getattr(ref, "remote_head", ref.name) == config.branch:
                        target = ref
                        break
        if last_seen_sha:
            summary.since_last_run = True
            new_commits = _commits_since_sha(
                repo, target, last_seen_sha, config.max_commits
            )
            if new_commits:
                summary.head_sha = new_commits[0].hexsha
            else:
                # No new commits; head is still last_seen (or current HEAD)
                try:
                    head_commit = next(repo.iter_commits(target, max_count=1))
                    summary.head_sha = head_commit.hexsha
                except StopIteration:
                    summary.head_sha = last_seen_sha
            summary.commits = _commits_to_infos(new_commits, config.max_commits)
        else:
            commits = list(repo.iter_commits(target, max_count=config.max_commits))
            if commits:
                summary.head_sha = commits[0].hexsha
            summary.commits = _commits_to_infos(commits, config.max_commits)
        if config.include_tags:
            summary.tags = _tags_to_infos(repo)
    except GitCommandError as e:
        summary.error = str(e).split("\n")[0]
    except Exception as e:
        summary.error = str(e)
    return summary
