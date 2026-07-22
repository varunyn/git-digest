"""Format repo summaries as text report."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Literal

from git_updates.fetcher import RepoSummary

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a concise technical summarizer. Given raw git update data
(commits and tags per repo), write a short digest: what changed, notable commits or
releases, and concrete highlights. Prioritize features, fixes, breaking changes,
release tags, and errors when the data supports them. Keep it scannable and under
300 words. Use plain text, no markdown headers. Do not invent details."""

OutputFormat = Literal["text", "markdown", "json"]


def _generated_at() -> str:
    """Return a timezone-aware, machine-readable generation timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _change_counts(summaries: list[RepoSummary]) -> dict[str, int]:
    """Return a small, presentation-ready count of report signals."""
    return {
        "repositories": len(summaries),
        "changed_repositories": sum(bool(s.commits or s.tags) for s in summaries),
        "commits": sum(len(s.commits) for s in summaries),
        "tags": sum(len(s.tags) for s in summaries),
        "errors": sum(s.error is not None for s in summaries),
    }


def _commit_type(subject: str) -> str | None:
    """Extract a Conventional Commit type, when a subject provides one."""
    prefix = subject.split(":", 1)[0].strip().lower()
    if "(" in prefix:
        prefix = prefix.split("(", 1)[0]
    known_types = {
        "feat",
        "fix",
        "perf",
        "refactor",
        "docs",
        "test",
        "build",
        "ci",
        "chore",
    }
    return prefix if prefix in known_types else None


def _signals(summary: RepoSummary) -> str:
    """Human-readable, evidence-based highlights for a repository."""
    types = Counter(filter(None, (_commit_type(commit.subject) for commit in summary.commits)))
    parts: list[str] = []
    if types:
        parts.append(", ".join(f"{count} {kind}" for kind, count in sorted(types.items())))
    if summary.tags:
        parts.append(f"{len(summary.tags)} release tag{'s' if len(summary.tags) != 1 else ''}")
    return "; ".join(parts)


def _raw_context(summaries: list[RepoSummary]) -> str:
    """Build raw context string for AI (no title/date)."""
    lines: list[str] = []
    for s in summaries:
        lines.append(f"## {s.display_name} ({s.url})")
        lines.append(f"  Branch: {s.branch}")
        if s.error:
            lines.append(f"  Error: {s.error}")
            lines.append("")
            continue
        if s.commits:
            header = "New commits since last run:" if s.since_last_run else "Recent commits:"
            lines.append(f"  {header}")
            for c in s.commits:
                ref_part = f" [{c.refs}]" if c.refs else ""
                lines.append(
                    f"    - {c.date_iso}  {c.sha_short}{ref_part}  {c.author}: {c.subject}"
                )
        elif s.since_last_run:
            lines.append("  No new commits since last run.")
        if s.tags_since_last_run:
            if s.tags:
                lines.append("  New tags/releases since last run:")
                for t in s.tags[:5]:
                    msg_part = f"  — {t.message}" if t.message else ""
                    lines.append(f"    - {t.date_iso}  {t.name} ({t.sha_short}){msg_part}")
            else:
                lines.append("  No new tags since last run.")
        elif s.tags:
            lines.append("  Recent tags/releases:")
            for t in s.tags[:5]:
                msg_part = f"  — {t.message}" if t.message else ""
                lines.append(f"    - {t.date_iso}  {t.name} ({t.sha_short}){msg_part}")
        lines.append("")
    return "\n".join(lines)


def _report_data(
    summaries: list[RepoSummary], title: str | None, generated_at: str
) -> dict[str, object]:
    """Build the versioned, JSON-safe representation shared by all renderers."""
    repos: list[dict[str, object]] = []
    for summary in summaries:
        signals = _signals(summary)
        repos.append(
            {
                "name": summary.display_name,
                "url": summary.url,
                "branch": summary.branch,
                "status": "error" if summary.error else "ok",
                "error": summary.error,
                "since_last_run": summary.since_last_run,
                "tags_since_last_run": summary.tags_since_last_run,
                "head_sha": summary.head_sha,
                "newest_tag_date": summary.newest_tag_date,
                "signals": signals.split("; ") if signals else [],
                "commits": [
                    {
                        "sha": commit.sha_short,
                        "author": commit.author,
                        "date": commit.date_iso,
                        "subject": commit.subject,
                        "refs": commit.refs,
                        "type": _commit_type(commit.subject),
                    }
                    for commit in summary.commits
                ],
                "tags": [
                    {
                        "name": tag.name,
                        "sha": tag.sha_short,
                        "date": tag.date_iso,
                        "message": tag.message,
                    }
                    for tag in summary.tags
                ],
            }
        )
    return {
        "schema_version": 1,
        "title": title,
        "generated_at": generated_at,
        "summary": _change_counts(summaries),
        "repositories": repos,
    }


def format_json_report(summaries: list[RepoSummary], title: str | None = None) -> str:
    """Render a stable, machine-readable report suitable for automation."""
    return json.dumps(_report_data(summaries, title, _generated_at()), indent=2, sort_keys=True)


def format_markdown_report(summaries: list[RepoSummary], title: str | None = None) -> str:
    """Render a scannable Markdown report suitable for chat and issue trackers."""
    counts = _change_counts(summaries)
    lines = [f"# {title or 'Git updates summary'}", "", f"Generated: {_generated_at()}", ""]
    lines.append(
        "**Signals:** "
        f"{counts['commits']} commits across "
        f"{counts['changed_repositories']} changed repositories; "
        f"{counts['tags']} release tags; {counts['errors']} errors."
    )
    for summary in summaries:
        lines.extend(["", f"## {summary.display_name}", "", f"`{summary.branch}` · {summary.url}"])
        if summary.error:
            lines.extend(["", f"> **Error:** {summary.error}"])
            continue
        signals = _signals(summary)
        if signals:
            lines.extend(["", f"**Highlights:** {signals}."])
        if summary.commits:
            label = "New commits" if summary.since_last_run else "Recent commits"
            lines.extend(["", f"### {label}", ""])
            for commit in summary.commits:
                refs = f" — `{commit.refs}`" if commit.refs else ""
                lines.append(
                    f"- `{commit.sha_short}` {commit.subject} — {commit.author} "
                    f"({commit.date_iso}){refs}"
                )
        elif summary.since_last_run:
            lines.extend(["", "No new commits since last run."])
        if summary.tags:
            label = "New releases" if summary.tags_since_last_run else "Recent releases"
            lines.extend(["", f"### {label}", ""])
            for tag in summary.tags:
                message = f" — {tag.message}" if tag.message else ""
                lines.append(f"- `{tag.name}` (`{tag.sha_short}`, {tag.date_iso}){message}")
        elif summary.tags_since_last_run:
            lines.extend(["", "No new release tags since last run."])
    return "\n".join(lines) + "\n"


def _format_text_report(summaries: list[RepoSummary], title: str | None = None) -> str:
    """
    Format a list of repo summaries as a plain-text report.

    Suitable for cron output (stdout or email).
    """
    lines: list[str] = []
    if title:
        lines.append(title)
        lines.append("=" * min(60, len(title)))
        lines.append("")
    now = _generated_at()
    lines.append(f"Generated: {now}")
    counts = _change_counts(summaries)
    lines.append(
        f"Signals: {counts['commits']} commits, {counts['tags']} release tags, "
        f"{counts['changed_repositories']} changed repos, {counts['errors']} errors"
    )
    lines.append("")

    for s in summaries:
        lines.append(f"## {s.display_name}")
        lines.append(f"  URL: {s.url}")
        lines.append(f"  Branch: {s.branch}")
        if s.error:
            lines.append(f"  Error: {s.error}")
            lines.append("")
            continue
        signals = _signals(s)
        if signals:
            lines.append(f"  Highlights: {signals}.")
        if s.commits:
            header = "New commits since last run:" if s.since_last_run else "Recent commits:"
            lines.append(f"  {header}")
            for c in s.commits:
                ref_part = f" [{c.refs}]" if c.refs else ""
                lines.append(
                    f"    - {c.date_iso}  {c.sha_short}{ref_part}  {c.author}: {c.subject}"
                )
        elif s.since_last_run:
            lines.append("  No new commits since last run.")
        if s.tags_since_last_run:
            if s.tags:
                lines.append("  New tags/releases since last run:")
                for t in s.tags[:5]:
                    msg_part = f"  — {t.message}" if t.message else ""
                    lines.append(f"    - {t.date_iso}  {t.name} ({t.sha_short}){msg_part}")
            else:
                lines.append("  No new tags since last run.")
        elif s.tags:
            lines.append("  Recent tags/releases:")
            for t in s.tags[:5]:
                msg_part = f"  — {t.message}" if t.message else ""
                lines.append(f"    - {t.date_iso}  {t.name} ({t.sha_short}){msg_part}")
        lines.append("")

    return "\n".join(lines)


def format_report(
    summaries: list[RepoSummary],
    title: str | None = None,
    *,
    output_format: OutputFormat = "text",
) -> str:
    """Render a report in text, Markdown, or stable JSON format."""
    if output_format == "text":
        return _format_text_report(summaries, title)
    if output_format == "markdown":
        return format_markdown_report(summaries, title)
    if output_format == "json":
        return format_json_report(summaries, title)
    raise ValueError(f"Unsupported output format: {output_format}")


def format_report_with_ai(
    summaries: list[RepoSummary],
    title: str | None = None,
    *,
    ollama_base_url: str = "http://127.0.0.1:11434",
    ollama_model: str = "gemma3n",
    ollama_timeout: int = 120,
) -> str:
    """
    Build raw context from summaries, send to Ollama for a short digest, return formatted report.

    On Ollama failure (unreachable, timeout, etc.) falls back to plain format_report.
    """
    from git_updates.ollama_client import generate

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    context = _raw_context(summaries)
    if not context.strip():
        return format_report(summaries, title=title)

    prompt = f"Summarize these git updates into a short digest.\n\n{context}"
    try:
        ai_text = generate(
            prompt,
            base_url=ollama_base_url,
            model=ollama_model,
            system=SYSTEM_PROMPT,
            stream=False,
            timeout=ollama_timeout,
        )
    except Exception as e:
        hint = ""
        if hasattr(e, "response") and getattr(e.response, "status_code", None) == 404:
            from git_updates.ollama_client import list_models

            available = list_models(ollama_base_url)
            if available:
                hint = (
                    f" Model '{ollama_model}' not found. Available: {', '.join(available)}. "
                    "Use --ollama-model <name>."
                )
        logger.warning("Ollama summarization failed (%s).%s Using plain report.", e, hint)
        return format_report(summaries, title=title)

    if not ai_text:
        return format_report(summaries, title=title)

    lines: list[str] = []
    if title:
        lines.append(title)
        lines.append("=" * min(60, len(title)))
        lines.append("")
    lines.append(f"Generated: {now}")
    lines.append("")
    lines.append(ai_text.strip())
    lines.append("")
    return "\n".join(lines)
