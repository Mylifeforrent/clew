"""In-memory sliding-window rate limiting for AI routes (doc 08 R11): no third-party dependencies, throttled per username.

Sufficient for a single-process single-host deployment; the window is counted
in process memory, so a multi-process deployment needs external storage (doc 08
§5 explicitly rules this out). Role checks reuse ``security.require_role``; the
dependency returned by the limiter factory performs "authentication + role
threshold + throttling" together, raising 429 with a ``Retry-After`` header
when exceeded.
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException

from ..security import require_role

# Default limits: chat 10 requests/60s, lineage suggestions 6 requests/60s
# (doc 08 §3 R11; [TBD-OPS] tune thresholds based on usage)
CHAT_WINDOW_SECONDS = 60
CHAT_MAX_REQUESTS = 10
SUGGEST_WINDOW_SECONDS = 60
SUGGEST_MAX_REQUESTS = 6


class _SlidingWindow:
    """Per-key sliding-window counter: overflow raises 429 with a Retry-After header."""

    def __init__(self, window_seconds: float, max_requests: int):
        self._window = float(window_seconds)
        self._max = max_requests
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self._window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self._max:
                retry_after = max(1, math.ceil(self._window - (now - hits[0])))
                raise HTTPException(
                    429,
                    "AI requests are too frequent; please retry later",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        """Clear all counters (for test isolation)."""
        with self._lock:
            self._hits.clear()


def ai_limiter(window_seconds: float, max_requests: int,
               role: str = "viewer"):
    """Build an AI route rate-limit dependency: authentication + role threshold + sliding-window throttling, returning the user dict.

    The returned dependency carries ``reset()`` (clears all counters in this
    bucket, for test isolation).
    """

    bucket = _SlidingWindow(window_seconds, max_requests)
    guard = require_role(role)

    def dependency(user: dict = Depends(guard)) -> dict:
        bucket.check(user["username"])
        return user

    dependency.reset = bucket.reset  # Function-object attribute: expose counter clearing on the instance
    return dependency
