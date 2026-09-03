"""Fetch repo data (commits and tags) from git remotes."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from git import Repo
from git.exc import BadName, GitCommandError

from git_updates.config import RepoConfig

if TYPE_CHECKING:
    from git import Commit


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
    tags_since_last_run: bool = False
    head_sha: str | None = None
    newest_tag_date: str | None = None
    # Stable tag identities (``name:target_sha``) currently present in the remote.
    tag_ids: list[str] = field(default_factory=list)
    # True when more unseen commits exist than the configured report limit.
    commits_truncated: bool = False

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
    """Return a readable, collision-resistant cache directory name for a URL."""
    name = _repo_name_from_url(url).replace("/", "_").replace(":", "_")
    safe_name = re.sub(r"[^\w.-]", "_", name)
    digest = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:12]
    return f"{safe_name}-{digest}"


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
        raw_message = c.message or ""
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8", errors="replace")
        result.append(
            CommitInfo(
                sha_short=c.hexsha[:7],
                author=c.author.name or "",
                date_iso=(
                    c.committed_datetime.strftime("%Y-%m-%d %H:%M") if c.committed_datetime else ""
                ),
                subject=raw_message.split("\n")[0].strip()[:80],
                refs=refs,
            )
        )
    return result


def _tag_commit_datetime_utc(tag) -> str | None:
    """Return tag's commit datetime as UTC ISO string for storage/comparison, or None."""
    from datetime import datetime

    dt = getattr(tag.commit, "committed_datetime", None)
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_utc_iso(s: str):
    """Parse UTC naive ISO datetime string for comparison."""
    from datetime import datetime

    return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")


def _tags_to_infos(
    repo: Repo,
    max_tags: int = 10,
    last_seen_tag_ids: set[str] | None = None,
    last_seen_newest_tag_date: str | None = None,
) -> tuple[list[TagInfo], str | None, list[str]]:
    """
    Get recent tags with commit date and message.

    ``last_seen_tag_ids`` uses ``name:target_sha`` identities, allowing tags created
    on old commits (and moved/recreated tags) to be detected reliably. The timestamp
    cutoff is retained only for legacy state that predates tag identities.
    Returns (tag_infos, newest_tag_date_iso, all_tag_ids) for state persistence.
    """
    from datetime import datetime

    result: list[TagInfo] = []
    tag_ids: list[str] = []
    newest_date_iso: str | None = None
    cutoff = None
    if last_seen_newest_tag_date:
        try:
            cutoff = _parse_utc_iso(last_seen_newest_tag_date)
        except (ValueError, TypeError):
            cutoff = None
    try:
        tags = sorted(
            repo.tags,
            key=lambda t: t.commit.committed_datetime or datetime.min,
            reverse=True,
        )
    except Exception:
        return result, newest_date_iso, tag_ids
    for tag in tags:
        try:
            commit = tag.commit
            tag_id = f"{tag.name}:{commit.hexsha}"
            tag_ids.append(tag_id)
            if last_seen_tag_ids is not None:
                if tag_id in last_seen_tag_ids:
                    continue
            if len(result) >= max_tags:
                # Keep collecting all identities for state, while bounding report
                # output just as the initial-report behavior does.
                continue
            dt = getattr(commit, "committed_datetime", None)
            if dt is None:
                continue
            tag_date_utc_str = _tag_commit_datetime_utc(tag)
            if tag_date_utc_str is None:
                continue
            if last_seen_tag_ids is None and cutoff is not None:
                try:
                    tag_dt = _parse_utc_iso(tag_date_utc_str)
                    if tag_dt <= cutoff:
                        if newest_date_iso is None:
                            newest_date_iso = tag_date_utc_str
                        continue
                except (ValueError, TypeError):
                    pass
            date_str = dt.strftime("%Y-%m-%d %H:%M") if dt else ""
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
            if newest_date_iso is None:
                newest_date_iso = tag_date_utc_str
        except Exception:
            continue
    if tags:
        try:
            newest_date_iso = _tag_commit_datetime_utc(tags[0])
        except Exception:
            pass
    return result, newest_date_iso, tag_ids


def _remote_target(repo: Repo, config: RepoConfig):
    """Fetch and resolve the configured branch to a remote-tracking commit."""
    origin = repo.remotes.origin
    if config.branch != "HEAD":
        remote_ref = f"refs/remotes/origin/{config.branch}"
        origin.fetch(refspec=f"+refs/heads/{config.branch}:{remote_ref}", tags=True)
        return repo.commit(remote_ref)

    origin.fetch(tags=True)
    # A normal clone's active branch tracks origin/<default>. Prefer that ref because
    # ``repo.head`` points at the stale local branch after fetch.
    try:
        tracking = repo.active_branch.tracking_branch()
        if tracking is not None:
            return repo.commit(tracking.path)
    except (TypeError, BadName):
        pass
    try:
        return repo.commit("refs/remotes/origin/HEAD")
    except BadName:
        return repo.head.commit


def _history_contains(repo: Repo, target: Any, commit_sha: str) -> bool:
    """Return whether the target's fetched history contains ``commit_sha``."""
    try:
        # GitPython's stubs type is_ancestor(Commit, Commit) but it accepts
        # SHA strings at runtime (passed through to `git merge-base`).
        return repo.is_ancestor(commit_sha, target)  # type: ignore[arg-type]
    except (BadName, GitCommandError):
        return False


def _deepen_until_contains(repo: Repo, config: RepoConfig, target: Any, commit_sha: str) -> Any:
    """Deepen a shallow clone in bounded steps until its previous state is visible."""
    is_shallow = repo.git.rev_parse("--is-shallow-repository").strip() == "true"
    if _history_contains(repo, target, commit_sha) or not is_shallow:
        return target
    origin = repo.remotes.origin
    for _ in range(5):
        if config.branch == "HEAD":
            origin.fetch(deepen=100, tags=True)
        else:
            remote_ref = f"refs/remotes/origin/{config.branch}"
            origin.fetch(refspec=f"+refs/heads/{config.branch}:{remote_ref}", deepen=100, tags=True)
        target = _remote_target(repo, config)
        if _history_contains(repo, target, commit_sha):
            break
    if not _history_contains(repo, target, commit_sha):
        raise RuntimeError(
            "Last-seen commit is unavailable after deepening the shallow clone; "
            "state was not advanced."
        )
    return target


def _commits_since_sha(
    repo: Repo,
    target: Any,
    last_seen_sha: str,
    max_count: int,
) -> tuple[list[Commit], bool]:
    """Return unseen commits and whether the configured report limit truncated them."""
    new_commits: list[Commit] = []
    for c in repo.iter_commits(target):
        if c.hexsha == last_seen_sha or c.hexsha.startswith(last_seen_sha):
            return new_commits, False
        if len(new_commits) >= max_count:
            return new_commits, True
        new_commits.append(c)
    # This should only occur for a rewritten remote; the preflight ancestry check
    # normally turns that situation into an error before we get here.
    return new_commits, False


def fetch_repo_summary(
    config: RepoConfig,
    cache_dir: Path,
    last_seen_sha: str | None = None,
    last_seen_tag_ids: set[str] | None = None,
    last_seen_newest_tag_date: str | None = None,
) -> RepoSummary:
    """
    Fetch latest commits and optional tags for one repo.

    Clones to cache_dir if needed (shallow), then fetches and builds summary.
    If last_seen_sha is set, only commits newer than that are included (for --changes-only).
    If last_seen_newest_tag_date is set (and include_tags), only tags with commit date
    after that are included (true new releases since last run).
    """
    name = _repo_name_from_url(config.url)
    summary = RepoSummary(url=config.url, name=name, branch=config.branch)

    try:
        repo_path = _ensure_cloned(cache_dir, config)
        repo = Repo(repo_path)
        target = _remote_target(repo, config)
        if last_seen_sha:
            summary.since_last_run = True
            target = _deepen_until_contains(repo, config, target, last_seen_sha)
            new_commits, summary.commits_truncated = _commits_since_sha(
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
            tag_ids = last_seen_tag_ids if last_seen_sha else None
            tag_cutoff = last_seen_newest_tag_date if last_seen_sha and tag_ids is None else None
            summary.tags, summary.newest_tag_date, summary.tag_ids = _tags_to_infos(
                repo,
                max_tags=10,
                last_seen_tag_ids=tag_ids,
                last_seen_newest_tag_date=tag_cutoff,
            )
            if last_seen_sha is not None:
                summary.tags_since_last_run = True
    except GitCommandError as e:
        summary.error = str(e).split("\n")[0]
    except Exception as e:
        summary.error = str(e)
    return summary
