"""Minimal in-process sliding-window rate limiter.

It is intentionally dependency-free and per-process: good enough to slow down
credential stuffing on a single uvicorn worker. For multi-worker / multi-host
deployments back it with Redis or enforce the limit at the edge.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

logger = logging.getLogger(__name__)

CleanupHook = Callable[[], None]


class SlidingWindowRateLimiter:
    def __init__(self, max_hits: int, window_seconds: int) -> None:
        self.max_hits = max_hits
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, ip_address: str) -> None:
        """Record a request for an IP address. Raise 429 if they exceed the limit."""
        now = time.monotonic()
        time_window_start = now - self.window_seconds

        with self._lock:
            # Get the list of timestamps for this IP
            request_timestamps = self._hits[ip_address]

            # Remove old timestamps that are outside our time window
            while request_timestamps and request_timestamps[0] <= time_window_start:
                request_timestamps.popleft()

            # Check if the IP has made too many requests
            if len(request_timestamps) >= self.max_hits:
                time_until_reset = max(1, int(self.window_seconds - (now - request_timestamps[0])))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests, please try again later.",
                    headers={
                        "Retry-After": str(time_until_reset),
                        "X-RateLimit-Limit": str(self.max_hits),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            # Log the new request timestamp
            request_timestamps.append(now)

            # Periodically clean up old IPs to save memory
            self._cleanup_locked(time_window_start)

    def _cleanup_locked(self, time_window_start: float) -> None:
        """Remove IPs that haven't made requests recently to save memory."""

        # Don't spend CPU cycles cleaning up if memory usage is low
        if len(self._hits) < 10_000:
            return

        # Find IPs that are no longer active
        ips_to_remove = []
        for ip, timestamps in self._hits.items():
            # If the IP has no recent requests
            if not timestamps or timestamps[-1] <= time_window_start:
                ips_to_remove.append(ip)

        # Remove the inactive IPs
        for ip in ips_to_remove:
            del self._hits[ip]

        # Emergency fail-safe: If under a DDoS attack with millions of fake IPs,
        # clear everything to prevent the server from crashing due to Out of Memory.
        if len(self._hits) > 20_000:
            self._hits.clear()


_limiter = SlidingWindowRateLimiter(
    max_hits=settings.rate_limit_attempts,
    window_seconds=settings.rate_limit_window_seconds,
)


def client_key(request: Request) -> str:
    """Rate-limit key: the client IP, optionally taken from a trusted proxy."""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str) -> Callable[[Request], None]:
    """Dependency factory: `Depends(rate_limit("login"))`.

    Allowed requests also carry `X-RateLimit-Limit` so clients can see the
    budget before they exhaust it; blocked ones add `Retry-After` and
    `X-RateLimit-Remaining: 0` (set inside `check`).
    """

    def dependency(request: Request, response: Response) -> None:
        if settings.is_test:
            return
        key = f"{scope}:{client_key(request)}"
        response.headers.setdefault("X-RateLimit-Limit", str(_limiter.max_hits))
        try:
            _limiter.check(key)
        except HTTPException:
            logger.warning("Rate limit exceeded: %s", key, extra={"scope": scope})
            raise

    return dependency
