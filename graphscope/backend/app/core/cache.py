from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from time import time
from typing import Any


@dataclass
class CacheEntry:
    expires_at: float
    value: Any


class TTLCache:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at < time():
                self._items.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = CacheEntry(
                expires_at=time() + self.ttl_seconds,
                value=value,
            )

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
