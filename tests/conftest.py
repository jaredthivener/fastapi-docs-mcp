"""Shared test fixtures."""

import pytest

from main import _cache


@pytest.fixture(autouse=True)
def _clear_cache() -> None:  # type: ignore[misc]
    """Clear the URL cache before and after each test."""
    _cache.clear()
    yield  # type: ignore[misc]
    _cache.clear()
