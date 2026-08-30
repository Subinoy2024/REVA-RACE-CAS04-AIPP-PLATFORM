"""Symmetric encryption helper (Fernet) for storing user secrets at rest.

Iteration-25 (Auto-Deploy):
    * Deployment platform PATs must never sit on disk in cleartext.
    * We use `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256).
    * The key is `AIPP_FERNET_KEY` — a 32-byte base64-encoded key.
      If missing, we auto-generate at process start and log a WARNING
      instructing the operator to persist it. On restart with a fresh
      key, previously stored tokens become undecryptable and the
      Integrations tab will show a clear "re-connect" prompt.

The module is intentionally tiny — the whole security story is: one key,
two functions.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from backend.core.logging import get_logger

logger = get_logger(__name__)

_ENV = "AIPP_FERNET_KEY"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = os.environ.get(_ENV, "").strip()
    if not key:
        key = Fernet.generate_key().decode()
        os.environ[_ENV] = key
        logger.warning(
            "aipp.crypto: %s was not set — generated an ephemeral key for this "
            "process. Set %s in .env to persist Integrations across restarts.",
            _ENV, _ENV,
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:  # pragma: no cover — bad key format
        raise RuntimeError(
            f"Invalid {_ENV}: must be a 32-byte base64-encoded Fernet key. "
            f"Generate one with: python -c 'from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())'"
        ) from e


def encrypt(plaintext: str) -> str:
    """Encrypt a string; returns a base64 token safe for a `Text` DB column."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a token produced by `encrypt`. Raises on tamper / wrong key."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise RuntimeError(
            "aipp.crypto: could not decrypt secret — the AIPP_FERNET_KEY has "
            "likely rotated. Re-onboard the affected integration."
        ) from e
