"""Small test doubles shared by several test files."""
from __future__ import annotations

import threading
from typing import Any


class FakeClock:
    """A clock whose sleep() moves time forward. Lets tests check timing without waiting."""

    def __init__(self, start: float = 1000.0):
        self.now = start
        self.sleeps: list[float] = []
        self._lock = threading.Lock()

    def time(self) -> float:
        with self._lock:
            return self.now

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)
            self.now += max(0.0, seconds)

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.now += seconds


class FakeBedrock:
    """Stands in for BedrockClient. Replies are queued per call, or computed by a function."""

    def __init__(self, replies: list[Any] | None = None, handler=None):
        self.replies = list(replies or [])
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def converse_json(self, *, model, system, user, max_tokens, schema, temperature=None):
        self.calls.append(
            {"model": model, "system": system, "user": user, "max_tokens": max_tokens,
             "schema": schema, "temperature": temperature}
        )
        if self.handler is not None:
            reply = self.handler(self.calls[-1])
        else:
            if not self.replies:
                raise AssertionError("FakeBedrock has no reply left for this call")
            reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
