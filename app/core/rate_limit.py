"""In-process sliding-window rate limiter.

Deliberately dependency-free and per-process: with multiple workers each
holds its own window, so the effective limit is (limit × workers) — still
plenty to stop online brute-force, which needs thousands of attempts.
Per-IP throttling across all endpoints belongs at the reverse proxy.
"""

import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        time_func=time.monotonic,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._now = time_func
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """Record one attempt for `key`.

        Returns None when allowed, otherwise the seconds to wait until the
        oldest counted attempt falls out of the window.
        """
        now = self._now()
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory under key churn
            self._prune(now)
        return None

    def _prune(self, now: float) -> None:
        for key, hits in list(self._hits.items()):
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if not hits:
                del self._hits[key]
