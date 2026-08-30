"""Security helpers: PAT handling, prompt-injection filter, upload validation."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from backend.core.config import get_settings

_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all )?previous (instructions|prompts)"),
    re.compile(r"(?i)disregard (the )?system prompt"),
    re.compile(r"(?i)you are now [a-z]+"),
    re.compile(r"(?i)developer mode"),
    re.compile(r"(?i)jailbreak"),
    re.compile(r"(?i)act as (a )?(system|admin|root)"),
    re.compile(r"(?i)reveal (your|the) (system prompt|api key|secret)"),
]


def sanitize_repository_snippet(text: str, *, max_chars: int = 4000) -> str:
    """Strip suspicious content and cap length before sending to the LLM.

    - Marks prompt-injection attempts inline so the LLM sees them as untrusted data.
    - Truncates to `max_chars` to keep prompts bounded.
    """
    if not text:
        return ""
    cleaned = text
    for pat in _INJECTION_PATTERNS:
        cleaned = pat.sub(lambda m: f"[UNTRUSTED_CONTENT: {m.group(0)}]", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n...[truncated]..."
    return cleaned


def validate_upload(filename: str, size: int, allowed_ext: Iterable[str] = (".log", ".txt", ".json")) -> None:
    """Raise ValueError if the uploaded file is too big or of a disallowed type."""
    settings = get_settings()
    if size > settings.max_log_upload_bytes:
        raise ValueError(
            f"Uploaded file exceeds max size ({size} > {settings.max_log_upload_bytes} bytes)"
        )
    lower = filename.lower()
    if not any(lower.endswith(ext) for ext in allowed_ext):
        raise ValueError(
            f"Uploaded file type not allowed. Accepted extensions: {', '.join(allowed_ext)}"
        )


def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", errors="ignore")
    return hashlib.sha256(data).hexdigest()


def looks_like_pat(value: str) -> bool:
    """Cheap sanity check that a string looks like a GitHub PAT."""
    if not value:
        return False
    if value.startswith(("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_")):
        return True
    return len(value) >= 40 and re.match(r"^[A-Za-z0-9_\-]+$", value) is not None
