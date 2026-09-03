"""CLI entry point for git-digest."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from git_updates.config import DEFAULT_CONFIG_PATHS, Config, load_dotenv_for_app
from git_updates.delivery import deliver_webhook
from git_updates.initializer import initialize_config
from git_updates.service import collect_updates, doctor_report, validate_config_file
from git_updates.summary import format_report, format_report_with_ai

logger = logging.getLogger("git_updates")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch latest git updates (commits, releases) from configured repos "
            "and print a summary."
        ),
    )
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        metavar="FILE",
        help="Path to YAML config file (repos list and options).",
    )
    parser.add_argument(
        "--init",
        type=Path,
        nargs="?",
        const=Path("repos.yaml"),
        metavar="FILE",
        help="Create a starter config (default: ./repos.yaml) and exit.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate config and exit.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run read-only environment checks (config, cache, git, state, Ollama) and exit.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --init to replace an existing config file.",
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
        "--format",
        choices=("text", "markdown", "json"),
        default="text",
        help="Report format (default: text). JSON is stable for automation.",
    )
    parser.add_argument(
        "--webhook-url",
        metavar="URL",
        help="POST the completed report to this webhook URL.",
    )
    parser.add_argument(
        "--webhook-timeout",
        type=int,
        default=15,
        metavar="SECS",
        help="Webhook request timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit nonzero when any repository could not be fetched.",
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
        help=(
            "Only show commits and tags new since last run "
            "(persists last-seen commit and tag names per repo)."
        ),
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

    if args.init:
        try:
            path = initialize_config(args.init, overwrite=args.force)
        except FileExistsError as e:
            logger.error("%s", e)
            return 2
        except OSError as e:
            logger.error("Could not create config: %s", e)
            return 1
        print(f"Created starter configuration: {path}")
        return 0

    if args.force:
        logger.error("--force may only be used with --init.")
        return 2
    if args.webhook_timeout < 1:
        logger.error("--webhook-timeout must be a positive integer.")
        return 2

    if args.validate:
        valid, message = validate_config_file(args.config)
        if valid:
            print(message)
            return 0
        print(message, file=sys.stderr)
        return 2

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

    if args.doctor:
        if args.ollama_url is not None:
            config.ollama_url = args.ollama_url
        if args.ollama_model is not None:
            config.ollama_model = args.ollama_model
        failed = False
        for name, ok, detail in doctor_report(config):
            label = "PASS" if ok is True else ("WARN" if ok is None else "FAIL")
            if ok is False:
                failed = True
            print(f"{label}: {name} - {detail}")
        return 1 if failed else 0

    title = args.title if args.title is not None else config.default_title
    ollama_model = args.ollama_model if args.ollama_model is not None else config.ollama_model
    ollama_url = args.ollama_url if args.ollama_url is not None else config.ollama_url
    ollama_timeout = (
        args.ollama_timeout if args.ollama_timeout is not None else config.ollama_timeout
    )

    summaries = collect_updates(config, changes_only=args.changes_only, verbose=args.verbose)

    if args.ai_summary:
        if args.format != "text":
            logger.error("--ai-summary currently supports only --format text.")
            return 2
        report = format_report_with_ai(
            summaries,
            title=title,
            ollama_base_url=ollama_url,
            ollama_model=ollama_model,
            ollama_timeout=ollama_timeout,
        )
    else:
        report = format_report(summaries, title=title, output_format=args.format)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
        if args.verbose:
            logger.info("Wrote report to %s", args.output)
    else:
        print(report)

    if args.webhook_url:
        try:
            deliver_webhook(
                report,
                args.webhook_url,
                output_format=args.format,
                timeout=args.webhook_timeout,
            )
        except Exception as e:
            logger.error("Webhook delivery failed: %s", e)
            return 1

    return 1 if args.fail_on_error and any(summary.error for summary in summaries) else 0


if __name__ == "__main__":
    sys.exit(main())
