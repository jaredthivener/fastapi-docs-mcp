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

from .config import ABSENT_TTL, CACHE_MAX_ENTRIES, CACHE_TTL

# key -> (stored_at_monotonic, value); a value of None records a confirmed-absent
# resource (kept for ABSENT_TTL rather than CACHE_TTL). Shares the LRU bound, so
# distinct missing paths can't grow it without limit.
_cache: OrderedDict[str, tuple[float, str | None]] = OrderedDict()
# key -> lock guarding the single-flight fetch for that key. Reaped in
# get_or_fetch as soon as the fetch it guards settles (see below) -- not
# here, and not on cache eviction/expiry: a key that's fetched but never
# cached (e.g. a confirmed-404) would otherwise never be cleaned up here,
# leaking one lock per distinct miss for the life of the process.
_locks: dict[str, asyncio.Lock] = {}


def _lookup(key: str) -> tuple[bool, str | None]:
    """Return ``(hit, value)``; ``hit`` with a ``None`` value is a cached absence."""
    entry = _cache.get(key)
    if entry is None:
        return False, None
    stored_at, value = entry
    ttl = CACHE_TTL if value is not None else ABSENT_TTL
    if time.monotonic() - stored_at > ttl:
        _cache.pop(key, None)
        return False, None
    _cache.move_to_end(key)  # mark most-recently-used
    return True, value


def cache_get(key: str) -> str | None:
    """Return a live cached value, or ``None`` if missing/expired/absent."""
    return _lookup(key)[1]


def cache_set(key: str, value: str | None) -> None:
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
    """Return cached value or run ``fetcher`` once, caching its result.

    A confirmed absence (``None``) is cached briefly (``ABSENT_TTL``); a raised
    exception is never cached, so a transient failure is retried.

    Single-flight: simultaneous callers for the same key await one fetch rather
    than each hitting the network.
    """
    hit, cached = _lookup(key)
    if hit:
        return cached

    lock = _lock_for(key)
    async with lock:
        try:
            # Double-check: another coroutine may have populated the cache
            # while we were waiting for the lock.
            hit, cached = _lookup(key)
            if hit:
                return cached

            value = await fetcher()
            cache_set(key, value)
            return value
        finally:
            # Reap the lock the instant this fetch settles -- hit, confirmed
            # miss, or exception alike -- so a key that never gets cached
            # can't accumulate a lock forever.
            if _locks.get(key) is lock:
                del _locks[key]
