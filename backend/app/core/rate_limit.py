"""Minimal in-process sliding-window rate limiter.

It is intentionally dependency-free and per-process: good enough to slow down
credential stuffing on a single uvicorn worker. For multi-worker / multi-host
deployments back it with Redis or enforce the limit at the edge.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import HTTPException, Request, status

from app.core.config import settings

CleanupHook = Callable[[], None]


class SlidingWindowRateLimiter:
    def __init__(self, max_hits: int, window_seconds: int) -> None:
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Record a hit for `key` or raise 429 when the window is exhausted."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_hits:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests, please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
            self._cleanup_locked(now, cutoff)

    def _cleanup_locked(self, now: float, cutoff: float) -> None:
        # Opportunistically drop empty buckets so memory stays flat.
        if len(self._hits) < 10_000:
            return
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            self._hits.pop(key, None)


_limiter = SlidingWindowRateLimiter(
    max_hits=settings.rate_limit_attempts,
    window_seconds=settings.rate_limit_window_seconds,
)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str) -> Callable[[Request], None]:
    """Dependency factory: `Depends(rate_limit("login"))`."""

    def dependency(request: Request) -> None:
        if settings.environment.lower() == "test":
            return
        _limiter.check(f"{scope}:{client_key(request)}")

    return dependency
