"""Tiny in-memory sliding-window rate limiter (per process; fine for a single small deployment)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int]:
        """Record a hit. Returns ``(allowed, retry_after_seconds)``. A limit <= 0 disables limiting."""
        if self.limit <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False, max(1, int(self.window - (now - hits[0])) + 1)
            hits.append(now)
            if len(self._hits) > 5000:  # bound memory under many distinct clients
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
            return True, 0
