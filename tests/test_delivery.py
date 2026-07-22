"""Tests for optional webhook delivery."""

from __future__ import annotations

from typing import Any

from git_updates.delivery import deliver_webhook


def test_deliver_webhook_posts_json_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class Response:
        def raise_for_status(self) -> None:
            captured["checked"] = True

    def fake_post(*args: Any, **kwargs: Any) -> Response:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("git_updates.delivery.requests.post", fake_post)

    deliver_webhook(
        '{"schema_version": 1}', "https://hooks.example.test/digest", output_format="json"
    )

    assert captured["args"] == ("https://hooks.example.test/digest",)
    assert captured["kwargs"]["headers"]["Content-Type"] == "application/json"
    assert captured["kwargs"]["timeout"] == 15
    assert captured["checked"] is True
