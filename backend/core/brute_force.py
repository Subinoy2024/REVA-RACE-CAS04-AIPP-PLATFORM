"""Brute-force protection for the login endpoint.

Design (in-memory, thesis scope; production-grade note in
`docs/PRODUCTION_HARDENING.md § 2`):

  - **IP-level rate limit** — 10 login attempts per minute per IP.
    Uses the existing `RateLimiter` primitive. Cheap DDoS filter.

  - **Email-level lockout** — 5 failed attempts (bad password) against
    the same email → lock that email for 15 minutes. Blunts a slow,
    distributed credential-stuffing attack that the IP filter alone
    would miss.

  - **Successful login clears both counters** — so the legitimate
    user is not punished after a typo.

Both stores are process-local. When we move to multi-replica the
lockout table should move to Redis (see PRODUCTION_HARDENING §2.1).
"""

from __future__ import annotations

import threading
import time
from typing import Dict

from fastapi import HTTPException, status

from backend.core.rate_limit import RateLimiter


_MAX_FAILS = 5
_LOCK_SECONDS = 15 * 60


class EmailLockoutTracker:
    def __init__(self) -> None:
        # email → (fail_count, first_fail_epoch)
        self._fails: Dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def is_locked(self, email: str) -> tuple[bool, int]:
        """Return (locked, seconds_remaining). Non-destructive."""
        with self._lock:
            state = self._fails.get(email)
            if state is None:
                return False, 0
            fails, first = state
            elapsed = time.monotonic() - first
            if elapsed >= _LOCK_SECONDS:
                self._fails.pop(email, None)
                return False, 0
            if fails >= _MAX_FAILS:
                return True, int(_LOCK_SECONDS - elapsed) + 1
            return False, 0

    def record_failure(self, email: str) -> None:
        with self._lock:
            state = self._fails.get(email)
            now = time.monotonic()
            if state is None:
                self._fails[email] = (1, now)
                return
            fails, first = state
            # Reset the window if the previous window has already elapsed.
            if now - first >= _LOCK_SECONDS:
                self._fails[email] = (1, now)
                return
            self._fails[email] = (fails + 1, first)

    def record_success(self, email: str) -> None:
        """Clear the counter so a legitimate user isn't punished for a typo."""
        with self._lock:
            self._fails.pop(email, None)

    def reset(self, email: str | None = None) -> None:
        with self._lock:
            if email is None:
                self._fails.clear()
            else:
                self._fails.pop(email, None)


# --- Shared instances -------------------------------------------------------
login_ip_limiter = RateLimiter(max_requests=10, window_seconds=60)
email_lockout = EmailLockoutTracker()


def enforce_email_not_locked(email: str) -> None:
    locked, retry_after = email_lockout.is_locked(email)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many failed sign-in attempts for this account. "
                f"Locked for {retry_after // 60} min {retry_after % 60}s."
            ),
            headers={"Retry-After": str(retry_after)},
        )
