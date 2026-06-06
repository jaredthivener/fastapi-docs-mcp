"""TTL + LRU cache with single-flight de-duplication.

Concurrent misses for the same key collapse into a single upstream fetch
(no thundering herd). Entries expire after ``CACHE_TTL`` and the cache is
bounded to ``CACHE_MAX_ENTRIES`` (oldest evicted first).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from .config import CACHE_MAX_ENTRIES, CACHE_TTL

# key -> (stored_at_monotonic, value)
_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
# key -> lock guarding the single-flight fetch for that key
_locks: dict[str, asyncio.Lock] = {}


def cache_get(key: str) -> str | None:
    """Return a live cached value, or ``None`` if missing/expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    stored_at, value = entry
    if time.monotonic() - stored_at > CACHE_TTL:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)  # mark most-recently-used
    return value


def cache_set(key: str, value: str) -> None:
    """Store a value, evicting the least-recently-used entry if over capacity."""
    _cache[key] = (time.monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX_ENTRIES:
        _cache.popitem(last=False)


def clear() -> None:
    """Drop all cached values and in-flight locks (used by tests)."""
    _cache.clear()
    _locks.clear()


def _lock_for(key: str) -> asyncio.Lock:
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def get_or_fetch(
    key: str, fetcher: Callable[[], Awaitable[str | None]]
) -> str | None:
    """Return cached value or run ``fetcher`` once, caching a successful result.

    Single-flight: simultaneous callers for the same key await one fetch rather
    than each hitting the network.
    """
    cached = cache_get(key)
    if cached is not None:
        return cached

    async with _lock_for(key):
        # Double-check: another coroutine may have populated the cache while we
        # were waiting for the lock.
        cached = cache_get(key)
        if cached is not None:
            return cached

        value = await fetcher()
        if value is not None:
            cache_set(key, value)
        return value
