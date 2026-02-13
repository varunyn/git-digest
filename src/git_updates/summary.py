"""Format repo summaries as text report."""

from __future__ import annotations

import logging
from datetime import datetime

from git_updates.fetcher import RepoSummary

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a concise technical summarizer. Given raw git update data (commits and tags per repo), write a short digest: what changed, notable commits or releases, and any highlights. Keep it scannable and under 300 words. Use plain text, no markdown headers. If there are no new commits for a repo, say so briefly."""


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
                lines.append(f"    - {c.date_iso}  {c.sha_short}{ref_part}  {c.author}: {c.subject}")
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


def format_report(summaries: list[RepoSummary], title: str | None = None) -> str:
    """
    Format a list of repo summaries as a plain-text report.

    Suitable for cron output (stdout or email).
    """
    lines: list[str] = []
    if title:
        lines.append(title)
        lines.append("=" * min(60, len(title)))
        lines.append("")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"Generated: {now}")
    lines.append("")

    for s in summaries:
        lines.append(f"## {s.display_name}")
        lines.append(f"  URL: {s.url}")
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
                lines.append(f"    - {c.date_iso}  {c.sha_short}{ref_part}  {c.author}: {c.subject}")
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
                hint = f" Model '{ollama_model}' not found. Available: {', '.join(available)}. Use --ollama-model <name>."
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
