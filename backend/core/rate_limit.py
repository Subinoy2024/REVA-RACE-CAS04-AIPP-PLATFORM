"""In-memory sliding-window rate limiter.

Why not Redis:
  - Thesis scope is single-process. In-memory is enough.
  - Adding Redis would drag ops complexity for zero research value.
  - Documented as a P1 production gap in docs/PRODUCTION_HARDENING.md.

Where it applies:
  - `POST /api/pipelines/generate`      — 5 requests / 60s per client IP
  - `POST /api/pipelines/generate/stream` — same bucket
  - `POST /api/pipeline-doctor/analyze` — 10 requests / 60s per client IP

How it works:
  - Per-key deque of request timestamps.
  - On each request, drop timestamps older than the window, count what
    remains, reject if the count exceeds the limit.
  - `_lock` guards the shared dict — FastAPI is async but the lock is
    threading.Lock() because we might be called from multiple event loops
    inside the same interpreter (uvicorn workers > 1).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max = max_requests
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Raise HTTP 429 if `key` has exceeded the quota."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            dq = self._hits[key]
            # drop old
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max:
                oldest = dq[0]
                retry_after = int(self.window - (now - oldest)) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Rate limit exceeded: {self.max} requests per "
                        f"{self.window}s. Retry in ~{retry_after}s."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)

    def reset(self, key: str | None = None) -> None:
        """Test helper — clear one key or the whole table."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


# --- Shared instances used by API routers -----------------------------------
generate_limiter = RateLimiter(max_requests=5, window_seconds=60)
rca_limiter = RateLimiter(max_requests=10, window_seconds=60)


def _client_key(request: Request) -> str:
    """Best-effort client identifier.

    Falls back to `client.host` when behind trusted proxies you should set
    `X-Forwarded-For` and honour it here — kept minimal for thesis scope.
    """
    fwd = request.headers.get("x-forwarded-for") or ""
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"


def enforce_generate_limit(request: Request) -> None:
    generate_limiter.check(_client_key(request))


def enforce_rca_limit(request: Request) -> None:
    rca_limiter.check(_client_key(request))
