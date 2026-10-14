"""Small in-memory helpers: a sliding-window rate limiter and a TTL cache.

In-memory is a deliberate choice: the service runs as a single process on one
VPS. If it ever ran as several replicas, both would move to Redis.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")

Clock = Callable[[], float]


class RateLimiter:
    """Allow at most `limit` events per `window` seconds per key."""

    def __init__(self, limit: int, window: float, clock: Clock = time.monotonic) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= now - self.window:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            # Forget idle clients so the dict can't grow without bound.
            if len(self._events) > 10_000:
                self._evict(now)
            return True

    def _evict(self, now: float) -> None:
        stale = [k for k, ev in self._events.items() if not ev or ev[-1] <= now - self.window]
        for key in stale:
            del self._events[key]


class TTLCache(Generic[T]):
    """Remember values for `ttl` seconds. Bounded to `max_items` entries."""

    def __init__(self, ttl: float, max_items: int = 1000, clock: Clock = time.monotonic) -> None:
        self.ttl = ttl
        self.max_items = max_items
        self._clock = clock
        self._data: dict[str, tuple[float, T]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            stored_at, value = item
            if self._clock() - stored_at > self.ttl:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            if len(self._data) >= self.max_items and key not in self._data:
                # Drop the oldest entry (dicts keep insertion order).
                self._data.pop(next(iter(self._data)))
            self._data[key] = (self._clock(), value)
