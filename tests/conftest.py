"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from fastapi_docs_mcp import cache


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    """Clear the URL cache (and in-flight locks) around each test."""
    cache.clear()
    yield
    cache.clear()
