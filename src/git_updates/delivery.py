"""Optional delivery helpers for git-digest reports."""

from __future__ import annotations

import requests


def deliver_webhook(report: str, url: str, *, output_format: str, timeout: int = 15) -> None:
    """POST a completed report to a user-provided webhook endpoint.

    The report is sent as the request body so generic automation endpoints can
    consume either the stable JSON report or a human-readable text/Markdown one.
    """
    content_type = "application/json" if output_format == "json" else "text/plain; charset=utf-8"
    response = requests.post(
        url,
        data=report.encode("utf-8"),
        headers={"Content-Type": content_type, "User-Agent": "git-digest"},
        timeout=timeout,
    )
    response.raise_for_status()
