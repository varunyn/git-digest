"""CLI entry point for git-digest."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from git_updates.config import Config, DEFAULT_CONFIG_PATHS, load_dotenv_for_app
from git_updates.fetcher import fetch_repo_summary
from git_updates.state import (
    get_last_seen_sha,
    get_last_seen_tag_names,
    load_state,
    save_state,
)
from git_updates.summary import format_report, format_report_with_ai

logger = logging.getLogger("git_updates")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch latest git updates (commits, releases) from configured repos and print a summary.",
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        metavar="FILE",
        help="Path to YAML config file (repos list and options).",
    )
    parser.add_argument(
        "--repos",
        "-r",
        type=Path,
        action="append",
        metavar="FILE",
        help="Path to a text file with one repo URL per line (can be repeated).",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        metavar="DIR",
        help="Directory to cache cloned repos (default: ~/.cache/git-digest).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        metavar="FILE",
        help="Write summary to file instead of stdout.",
    )
    parser.add_argument(
        "--title",
        "-t",
        type=str,
        default=None,
        metavar="TITLE",
        help="Title for the report (default: from config or GIT_DIGEST_DEFAULT_TITLE).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log progress to stderr.",
    )
    parser.add_argument(
        "--changes-only",
        action="store_true",
        help="Only show commits and tags new since last run (persists last-seen commit and tag names per repo).",
    )
    parser.add_argument(
        "--ai-summary",
        action="store_true",
        help="Use Ollama (local) to generate a short AI digest instead of raw commit list.",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default=None,
        metavar="MODEL",
        help="Ollama model name (default: from config or OLLAMA_MODEL).",
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=None,
        metavar="URL",
        help="Ollama base URL (default: from config or OLLAMA_BASE_URL).",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=None,
        metavar="SECS",
        help="Ollama request timeout in seconds (default: from config or OLLAMA_TIMEOUT).",
    )
    return parser.parse_args()


def main() -> int:
    """Run git-digest and return exit code."""
    load_dotenv_for_app()
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if args.config:
        try:
            config = Config.from_yaml(args.config)
        except FileNotFoundError as e:
            logger.error("%s", e)
            return 1
        except Exception as e:
            logger.error("Invalid config: %s", e)
            return 1
    elif args.repos:
        config = Config.from_repo_list(args.repos)
        if not config.repos:
            logger.error("No repos found in given files.")
            return 1
    else:
        loaded = False
        for p in DEFAULT_CONFIG_PATHS:
            if p.exists():
                try:
                    config = Config.from_yaml(p)
                    loaded = True
                    break
                except Exception as e:
                    logger.error("Failed to load %s: %s", p, e)
                    return 1
        if not loaded:
            logger.error(
                "No config found. Use --config FILE or --repos FILE, or create one of: %s",
                ", ".join(str(p) for p in DEFAULT_CONFIG_PATHS),
            )
            return 1

    config = config.with_env_overrides()
    if args.cache_dir:
        config.cache_dir = args.cache_dir.expanduser().resolve()
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    title = args.title if args.title is not None else config.default_title
    ollama_model = args.ollama_model if args.ollama_model is not None else config.ollama_model
    ollama_url = args.ollama_url if args.ollama_url is not None else config.ollama_url
    ollama_timeout = args.ollama_timeout if args.ollama_timeout is not None else config.ollama_timeout

    state = load_state(config.cache_dir) if args.changes_only else {}

    summaries: list = []
    for repo_config in config.repos:
        if args.verbose:
            logger.info("Fetching %s ...", repo_config.url)
        last_sha = get_last_seen_sha(state, repo_config.url) if args.changes_only else None
        last_tag_names = (
            get_last_seen_tag_names(state, repo_config.url) if args.changes_only else None
        )
        summary = fetch_repo_summary(
            repo_config,
            config.cache_dir,
            last_seen_sha=last_sha,
            last_seen_tag_names=last_tag_names or None,
        )
        summaries.append(summary)
        if args.changes_only and not summary.error:
            entry: dict = {}
            if summary.head_sha:
                entry["commit_sha"] = summary.head_sha
            if summary.recent_tag_names:
                entry["tag_names"] = summary.recent_tag_names
            if entry:
                state[repo_config.url] = entry
    if args.changes_only:
        save_state(config.cache_dir, state)

    if args.ai_summary:
        report = format_report_with_ai(
            summaries,
            title=title,
            ollama_base_url=ollama_url,
            ollama_model=ollama_model,
            ollama_timeout=ollama_timeout,
        )
    else:
        report = format_report(summaries, title=title)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        if args.verbose:
            logger.info("Wrote report to %s", args.output)
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
