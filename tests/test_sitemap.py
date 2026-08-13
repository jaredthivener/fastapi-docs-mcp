"""Tests for the discovery layer: sitemap fetch, keyword search, categorization."""

from __future__ import annotations

from fastapi_docs_mcp import sitemap
from fastapi_docs_mcp.config import BASE_URL


class TestSitemap:
    async def test_fetch_sitemap(self, mock_net: None) -> None:
        urls = await sitemap.fetch_sitemap()
        assert f"{BASE_URL}/tutorial/cors/" in urls

    async def test_fetch_sitemap_confirmed_absent(self, none_net: None) -> None:
        assert await sitemap.fetch_sitemap() == []

    async def test_search_direct(self, mock_net: None) -> None:
        assert "tutorial/cors" in await sitemap.search_sitemap_urls("cors")

    async def test_search_alias(self, mock_net: None) -> None:
        # "auth" is not a substring of any URL → alias maps to "security".
        result = await sitemap.search_sitemap_urls("auth")
        assert any("security" in p for p in result)

    async def test_search_empty_sitemap(self, none_net: None) -> None:
        assert await sitemap.search_sitemap_urls("cors") == []

    def test_categorize(self) -> None:
        cats = sitemap.categorize_urls(
            [
                f"{BASE_URL}/tutorial/cors/",
                f"{BASE_URL}/advanced/websockets/",
                f"{BASE_URL}/some-random-page/",
                f"{BASE_URL}/",
            ]
        )
        assert "tutorial/cors" in cats["tutorial"]
        assert "advanced/websockets" in cats["advanced"]
        assert "some-random-page" in cats["other"]
