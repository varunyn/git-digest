"""Tests for human and machine-readable report formatting."""

from __future__ import annotations

import json

from git_updates.fetcher import CommitInfo, RepoSummary, TagInfo
from git_updates.summary import format_report


def _summary() -> RepoSummary:
    return RepoSummary(
        url="https://github.com/acme/widget.git",
        name="acme/widget",
        branch="main",
        since_last_run=True,
        tags_since_last_run=True,
        head_sha="abcdef123",
        newest_tag_date="2026-07-22 12:00:00",
        commits=[
            CommitInfo(
                sha_short="abcdef1",
                author="Ada",
                date_iso="2026-07-22 11:30",
                subject="feat(api): add digest endpoint",
                refs="origin/main",
            ),
            CommitInfo(
                sha_short="abcdef2",
                author="Lin",
                date_iso="2026-07-22 10:30",
                subject="fix: preserve state",
            ),
        ],
        tags=[TagInfo(name="v1.2.0", sha_short="abcdef1", date_iso="2026-07-22 12:00")],
    )


def test_json_format_has_versioned_stable_structure() -> None:
    report = json.loads(format_report([_summary()], title="Daily", output_format="json"))

    assert report["schema_version"] == 1
    assert report["title"] == "Daily"
    assert report["summary"] == {
        "repositories": 1,
        "changed_repositories": 1,
        "commits": 2,
        "tags": 1,
        "errors": 0,
    }
    repo = report["repositories"][0]
    assert repo["status"] == "ok"
    assert repo["commits"][0]["type"] == "feat"
    assert repo["tags"][0]["name"] == "v1.2.0"
    assert "T" in report["generated_at"]


def test_markdown_format_includes_actionable_signals() -> None:
    report = format_report([_summary()], title="Daily", output_format="markdown")

    assert report.startswith("# Daily\n")
    assert (
        "**Signals:** 2 commits across 1 changed repositories; 1 release tags; 0 errors." in report
    )
    assert "**Highlights:** 1 feat, 1 fix; 1 release tag." in report
    assert "- `abcdef1` feat(api): add digest endpoint" in report
    assert "### New releases" in report


def test_text_format_surfaces_errors_and_summary_counts() -> None:
    failed = RepoSummary(
        url="https://example.test/broken.git",
        name="broken",
        branch="main",
        error="authentication failed",
    )
    report = format_report([_summary(), failed], title="Daily")

    assert "Signals: 2 commits, 1 release tags, 1 changed repos, 1 errors" in report
    assert "Highlights: 1 feat, 1 fix; 1 release tag." in report
    assert "Error: authentication failed" in report
