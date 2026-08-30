"""Shared HTTP client for talking to the AIPP FastAPI backend from Gradio."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx

# Gradio and FastAPI both run inside the same pod — hit the backend locally.
BACKEND = os.environ.get("AIPP_INTERNAL_BACKEND_URL", "http://127.0.0.1:8001")

_client: httpx.Client | None = None


def client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(base_url=BACKEND, timeout=300.0)
    return _client


def get(path: str, *, token: str | None = None, **kwargs) -> Any:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client().get(path, headers=headers, **kwargs)
    r.raise_for_status()
    return r.json()


def post(path: str, *, token: str | None = None, **kwargs) -> Any:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client().post(path, headers=headers, **kwargs)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return r.json()


def delete(path: str, *, token: str | None = None, **kwargs) -> Any:
    headers = kwargs.pop("headers", {}) or {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client().delete(path, headers=headers, **kwargs)
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(f"HTTP {r.status_code}: {detail}")
    return r.json()


def sse_post(path: str, *, json_body: dict, timeout: float = 600.0) -> Iterator[dict]:
    """POST + read `text/event-stream` frames as dicts.

    Yields each decoded JSON event. Silently skips heartbeats / empty frames.
    """
    with httpx.stream(
        "POST", f"{BACKEND.rstrip('/')}{path}",
        json=json_body, timeout=timeout,
    ) as r:
        if r.status_code >= 400:
            body = r.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {r.status_code}: {body}")
        for line in r.iter_lines():
            if not line:
                continue
            # httpx.iter_lines returns str already; SSE prefix is "data: "
            if line.startswith("data:"):
                blob = line[5:].strip()
            else:
                blob = line.strip()
            if not blob:
                continue
            try:
                yield json.loads(blob)
            except json.JSONDecodeError:
                # ignore comment lines and malformed frames
                continue
