"""Token bucket used to keep Bedrock at no more than 1 request per second (design 9.2).

This is the second guard. The first is the queue: one worker Lambda, reserved concurrency 1,
batch size 1. The bucket starts empty, so the first call after a cold start waits one
refill period. That also covers a hand-off from a previous container.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

_EPSILON = 1e-9  # absorbs float rounding after a sleep


class TokenBucket:
    def __init__(
        self,
        rate_per_s: float = 1.0,
        capacity: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if rate_per_s <= 0 or capacity < 1:
            raise ValueError("rate_per_s must be positive and capacity at least 1")
        self.rate_per_s = float(rate_per_s)
        self.capacity = float(capacity)
        self._clock = clock
        self._sleep = sleep
        self._tokens = 0.0  # empty at start
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until one token is available, then take it."""
        while True:
            with self._lock:
                now = self._clock()
                elapsed = max(0.0, now - self._last)
                self._last = now
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_s)
                if self._tokens >= 1.0 - _EPSILON:
                    self._tokens = max(0.0, self._tokens - 1.0)
                    return
                wait = (1.0 - self._tokens) / self.rate_per_s
            self._sleep(wait)
