"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fastapi_docs_mcp import cache, http

from .fixtures import route


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Clear the URL cache (and in-flight locks) around each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def mock_net(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``http.fetch`` through the canned fixtures in ``tests/fixtures.py``."""

    async def fake_fetch(url: str) -> str | None:
        return route(url)

    monkeypatch.setattr(http, "fetch", fake_fetch)


@pytest.fixture
def none_net(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``http.fetch`` to confirmed-absent (``None``) for every URL."""

    async def fake_fetch(_url: str) -> None:
        return None

    monkeypatch.setattr(http, "fetch", fake_fetch)


@pytest.fixture
def unreachable_net(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``http.fetch`` to a transient failure (``UpstreamError``) for every URL."""

    async def fake_fetch(url: str) -> str:
        raise http.UpstreamError(f"simulated unreachable: {url}")

    monkeypatch.setattr(http, "fetch", fake_fetch)
