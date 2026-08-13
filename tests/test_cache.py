"""Tests for the TTL + LRU cache with single-flight de-duplication."""

from __future__ import annotations

import asyncio
import time

import pytest

from fastapi_docs_mcp import cache


class TestCache:
    def test_set_and_get(self) -> None:
        cache.cache_set("k", "v")
        assert cache.cache_get("k") == "v"

    def test_miss(self) -> None:
        assert cache.cache_get("absent") is None

    def test_expiry_evicts(self) -> None:
        cache._cache["old"] = (time.monotonic() - 1_000_000, "stale")
        assert cache.cache_get("old") is None
        assert "old" not in cache._cache

    def test_lru_eviction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("fastapi_docs_mcp.cache.CACHE_MAX_ENTRIES", 3)
        for i in range(5):
            cache.cache_set(f"k{i}", str(i))
        assert len(cache._cache) == 3
        assert "k0" not in cache._cache
        assert "k4" in cache._cache

    async def test_single_flight_caches(self) -> None:
        calls = 0

        async def fetcher() -> str:
            nonlocal calls
            calls += 1
            return "value"

        a = await cache.get_or_fetch("key", fetcher)
        b = await cache.get_or_fetch("key", fetcher)
        assert a == b == "value"
        assert calls == 1

    async def test_get_or_fetch_does_not_cache_none(self) -> None:
        async def fetcher() -> str | None:
            return None

        assert await cache.get_or_fetch("none-key", fetcher) is None
        assert "none-key" not in cache._cache

    async def test_get_or_fetch_does_not_cache_exception(self) -> None:
        # A failed fetch (e.g. http.UpstreamError) must not be cached — a
        # transient failure shouldn't poison the cache for the TTL window.
        calls = 0

        async def fetcher() -> str:
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cache.get_or_fetch("err-key", fetcher)
        assert "err-key" not in cache._cache

        with pytest.raises(RuntimeError):
            await cache.get_or_fetch("err-key", fetcher)
        assert calls == 2  # not single-flighted into a cached failure

    def test_expiry_cleans_locks(self) -> None:
        # Verify that when a cache entry expires, its lock is also cleaned up
        cache._cache["old"] = (time.monotonic() - 1_000_000, "stale")
        cache._locks["old"] = asyncio.Lock()
        assert "old" in cache._locks

        # Access the expired entry (triggers cleanup)
        assert cache.cache_get("old") is None

        # Verify both _cache and _locks are cleaned
        assert "old" not in cache._cache
        assert "old" not in cache._locks

    def test_lru_eviction_cleans_locks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Verify that when LRU eviction occurs, locks are also cleaned up
        monkeypatch.setattr("fastapi_docs_mcp.cache.CACHE_MAX_ENTRIES", 3)

        # Create locks for entries
        for i in range(5):
            cache.cache_set(f"k{i}", str(i))
            cache._locks[f"k{i}"] = asyncio.Lock()

        # Verify LRU eviction happened and locks were cleaned
        assert len(cache._cache) == 3
        assert "k0" not in cache._cache
        assert "k0" not in cache._locks
        assert "k1" not in cache._locks
        assert "k4" in cache._cache
        assert "k4" in cache._locks
