"""Thin client for Ollama generate API (local AI summarization)."""

from __future__ import annotations

import json
import logging
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "gemma3n"
DEFAULT_TIMEOUT = 120


def list_models(base_url: str = DEFAULT_BASE_URL, timeout: int = 10) -> list[str]:
    """
    Return list of installed Ollama model names (e.g. ['gemma3n:latest', 'nomic-embed-text:latest']).

    Returns empty list on any error (e.g. Ollama not running).
    """
    url = urljoin(base_url.rstrip("/") + "/", "api/tags")
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models") or []
        return [m.get("name", m.get("model", "")) for m in models if m.get("name") or m.get("model")]
    except Exception:
        return []


def generate(
    prompt: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
    stream: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """
    Call Ollama /api/generate and return the full response text.

    Args:
        prompt: User prompt (e.g. git update data to summarize).
        base_url: Ollama base URL (e.g. http://127.0.0.1:11434).
        model: Model name (e.g. llama3.2, mistral).
        system: Optional system prompt/instructions.
        stream: If True, stream chunks; if False, return complete response.
        timeout: Request timeout in seconds.

    Returns:
        Generated text from the "response" field.

    Raises:
        OllamaError: On API error or non-200 response.
        requests.RequestException: On connection/timeout errors.
    """
    url = urljoin(base_url.rstrip("/") + "/", "api/generate")
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
    }
    if system is not None:
        payload["system"] = system

    resp = requests.post(url, json=payload, timeout=timeout, stream=stream)
    resp.raise_for_status()

    if stream:
        text_parts: list[str] = []
        for line in resp.iter_lines():
            if line:
                data = json.loads(line.decode("utf-8"))
                if "response" in data:
                    text_parts.append(data["response"])
        return "".join(text_parts)

    data = resp.json()
    return (data.get("response") or "").strip()


class OllamaError(Exception):
    """Raised when Ollama API returns an error or is unreachable."""

    pass
