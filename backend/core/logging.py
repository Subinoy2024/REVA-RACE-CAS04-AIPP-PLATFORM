"""Structured logging configuration with credential redaction."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

from backend.core.config import get_settings

# Regex patterns for common secret shapes. Anything matching is replaced with `***REDACTED***`.
_SECRET_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),                # GitHub PAT / OAuth
    re.compile(r"github_pat_[A-Za-z0-9_]{40,}"),               # fine-grained GitHub PAT
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),                      # OpenAI / Emergent
    re.compile(r"AKIA[0-9A-Z]{16}"),                            # AWS access key id
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),                      # Google API key
    re.compile(r"(?i)(authorization|bearer|token)[=: ]+[A-Za-z0-9._\-]{16,}"),
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for pat in _SECRET_PATTERNS:
            msg = pat.sub("***REDACTED***", msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    if root.handlers:
        return
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    ))
    h.addFilter(RedactingFilter())
    root.addHandler(h)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def redact(value: Any) -> str:
    """Utility to redact secret material from strings before logging or persisting."""
    if not isinstance(value, str):
        return "***"
    s = value
    for pat in _SECRET_PATTERNS:
        s = pat.sub("***REDACTED***", s)
    return s
