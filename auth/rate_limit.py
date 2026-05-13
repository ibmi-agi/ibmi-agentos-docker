"""
Rate Limiter
============

In-memory sliding-window rate limiter using cachetools.

Keyed by API key hash (or IP for unauthenticated requests).
Resets on container restart — this is abuse prevention, not a security guarantee.
"""

from __future__ import annotations

import time
from collections import defaultdict
from os import getenv
from threading import Lock


def _parse_limit() -> tuple[int, int]:
    """Parse AUTH_RATE_LIMIT env var (format: ``requests/seconds``, default ``100/60``)."""
    raw = getenv("AUTH_RATE_LIMIT", "100/60")
    parts = raw.split("/")
    if len(parts) == 2:
        return int(parts[0]), int(parts[1])
    return 100, 60


class RateLimiter:
    """Sliding-window rate limiter.

    Thread-safe, in-memory. Each key tracks timestamps of recent requests
    within the configured window.
    """

    def __init__(
        self, max_requests: int | None = None, window_seconds: int | None = None
    ) -> None:
        default_max, default_window = _parse_limit()
        self.max_requests = max_requests or default_max
        self.window_seconds = window_seconds or default_window
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> tuple[bool, dict[str, str]]:
        """Check if a request is allowed.

        Returns:
            Tuple of (allowed, headers) where headers include rate limit info.
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            # Prune old entries
            timestamps = self._requests[key]
            self._requests[key] = [t for t in timestamps if t > cutoff]
            timestamps = self._requests[key]

            remaining = max(0, self.max_requests - len(timestamps))
            headers = {
                "X-RateLimit-Limit": str(self.max_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(now + self.window_seconds)),
            }

            if len(timestamps) >= self.max_requests:
                headers["Retry-After"] = str(self.window_seconds)
                return False, headers

            self._requests[key].append(now)
            headers["X-RateLimit-Remaining"] = str(remaining - 1)
            return True, headers

    def cleanup(self) -> None:
        """Remove expired entries. Call periodically if memory is a concern."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            empty_keys = []
            for key, timestamps in self._requests.items():
                self._requests[key] = [t for t in timestamps if t > cutoff]
                if not self._requests[key]:
                    empty_keys.append(key)
            for key in empty_keys:
                del self._requests[key]
