"""Tests for FastAPI Docs MCP Server."""

from unittest.mock import AsyncMock, patch

import httpx

from main import (
    _KEYWORD_ALIASES,
    BASE_URL,
    _cache,
    _cache_get,
    _cache_set,
    _search_sitemap_urls,
    categorize_urls,
    compare_fastapi_approaches,
    decode_html_entities,
    extract_code_blocks,
    extract_text_from_html,
    fetch_sitemap,
    fetch_url,
    get_fastapi_best_practices,
    get_fastapi_docs,
    get_fastapi_example,
    list_fastapi_pages,
    search_fastapi_docs,
    truncate_content,
)


class TestFetchUrl:
    """Tests for the fetch_url function."""

    async def test_fetch_valid_url(self) -> None:
        """Should successfully fetch a valid URL."""
        result = await fetch_url(BASE_URL)
        assert result is not None
        assert "FastAPI" in result

    async def test_fetch_invalid_url(self) -> None:
        """Should return None for invalid URLs."""
        result = await fetch_url(f"{BASE_URL}/nonexistent-page-12345")
        assert result is None


class TestExtractTextFromHtml:
    """Tests for the extract_text_from_html function."""

    def test_extracts_text_from_simple_html(self) -> None:
        """Should extract plain text from HTML."""
        html = "<p>Hello <b>world</b></p>"
        result = extract_text_from_html(html)
        assert "Hello" in result
        assert "world" in result
        assert "<p>" not in result
        assert "<b>" not in result

    def test_removes_script_tags(self) -> None:
        """Should remove script content."""
        html = "<p>Text</p><script>alert('xss')</script><p>More</p>"
        result = extract_text_from_html(html)
        assert "alert" not in result
        assert "Text" in result

    def test_decodes_html_entities(self) -> None:
        """Should decode common HTML entities."""
        html = "<p>&amp; &quot;text&quot;</p>"
        result = extract_text_from_html(html)
        assert "&" in result
        assert '"text"' in result

    def test_extracts_article_content(self) -> None:
        """Should prioritize article content when available."""
        html = "<nav>Menu</nav><article><p>Main content</p></article><footer>Footer</footer>"
        result = extract_text_from_html(html)
        assert "Main content" in result


class TestTruncateContent:
    """Tests for the truncate_content function."""

    def test_short_content_unchanged(self) -> None:
        """Should not truncate content under the limit."""
        content = "Short text"
        result = truncate_content(content, max_length=100)
        assert result == content

    def test_long_content_truncated(self) -> None:
        """Should truncate content over the limit."""
        content = "A" * 200
        result = truncate_content(content, max_length=100)
        assert len(result) < 200
        assert "truncated" in result.lower()

    def test_breaks_at_paragraph(self) -> None:
        """Should prefer breaking at paragraph boundaries."""
        content = "First paragraph.\n\n" + "A" * 50 + "\n\nThird paragraph."
        result = truncate_content(content, max_length=80)
        assert result.startswith("First paragraph.")


class TestCategorizeUrls:
    """Tests for the categorize_urls function."""

    def test_categorizes_tutorial_urls(self) -> None:
        """Should categorize tutorial URLs correctly."""
        urls = [f"{BASE_URL}/tutorial/first-steps/"]
        result = categorize_urls(urls)
        assert "tutorial/first-steps" in result["tutorial"]

    def test_categorizes_advanced_urls(self) -> None:
        """Should categorize advanced URLs correctly."""
        urls = [f"{BASE_URL}/advanced/websockets/"]
        result = categorize_urls(urls)
        assert "advanced/websockets" in result["advanced"]

    def test_handles_other_urls(self) -> None:
        """Should put uncategorized URLs in 'other'."""
        urls = [f"{BASE_URL}/some-random-page/"]
        result = categorize_urls(urls)
        assert "some-random-page" in result["other"]


class TestFetchSitemap:
    """Tests for the fetch_sitemap function."""

    async def test_fetches_sitemap(self) -> None:
        """Should fetch and parse the sitemap."""
        urls = await fetch_sitemap()
        assert len(urls) > 0
        assert all(url.startswith(BASE_URL) for url in urls)

    async def test_sitemap_contains_tutorial(self) -> None:
        """Should include tutorial pages in sitemap."""
        urls = await fetch_sitemap()
        tutorial_urls = [u for u in urls if "/tutorial/" in u]
        assert len(tutorial_urls) > 0


class TestGetFastapiDocs:
    """Tests for the get_fastapi_docs tool."""

    async def test_fetches_valid_page(self) -> None:
        """Should fetch documentation for a valid path."""
        # Access the underlying function via .fn attribute
        result = await get_fastapi_docs("tutorial/first-steps")
        assert "FastAPI" in result
        assert "tutorial/first-steps" in result

    async def test_handles_invalid_page(self) -> None:
        """Should return helpful message for invalid paths."""
        result = await get_fastapi_docs("nonexistent/page")
        assert "Could not find" in result or "list_fastapi_pages" in result


class TestSearchFastapiDocs:
    """Tests for the search_fastapi_docs tool."""

    async def test_finds_direct_match(self) -> None:
        """Should find pages matching the search term."""
        result = await search_fastapi_docs("cors")
        assert "cors" in result.lower()
        assert BASE_URL in result

    async def test_uses_keyword_aliases(self) -> None:
        """Should use keyword aliases for common terms."""
        result = await search_fastapi_docs("auth")
        assert "security" in result.lower()

    async def test_handles_no_results(self) -> None:
        """Should return helpful message when no results found."""
        result = await search_fastapi_docs("xyznonexistent123")
        assert "No results" in result or "list_fastapi_pages" in result


class TestListFastapiPages:
    """Tests for the list_fastapi_pages tool."""

    async def test_lists_pages(self) -> None:
        """Should list documentation pages."""
        result = await list_fastapi_pages()
        assert "Tutorial" in result
        assert "Advanced" in result
        assert "Total pages" in result

    async def test_includes_paths(self) -> None:
        """Should include actual page paths."""
        result = await list_fastapi_pages()
        assert "tutorial/" in result


class TestExtractCodeBlocks:
    """Tests for the extract_code_blocks function."""

    def test_extracts_pre_code_blocks(self) -> None:
        """Should extract code from pre/code blocks."""
        html = '<pre><code>def hello():\n    return "world"</code></pre>'
        result = extract_code_blocks(html)
        assert len(result) >= 1
        assert "def hello" in result[0]

    def test_handles_html_entities_in_code(self) -> None:
        """Should decode HTML entities in code blocks."""
        html = "<pre><code>def check_value(x, y):\n    if x &lt; 10 &amp;&amp; y &gt; 5:\n        return True</code></pre>"
        result = extract_code_blocks(html)
        assert len(result) >= 1
        assert "<" in result[0]  # &lt; should be decoded to <


class TestGetFastapiExample:
    """Tests for the get_fastapi_example tool."""

    async def test_gets_cors_example(self) -> None:
        """Should get code examples for CORS."""
        result = await get_fastapi_example("cors")
        assert "```python" in result
        assert "CORS" in result or "cors" in result.lower()

    async def test_gets_dependencies_example(self) -> None:
        """Should get code examples for dependencies."""
        result = await get_fastapi_example("dependencies")
        assert "```python" in result
        assert "Example" in result

    async def test_handles_unknown_topic(self) -> None:
        """Should return helpful message for unknown topics."""
        result = await get_fastapi_example("xyznonexistent")
        assert "No examples found" in result or "Try:" in result


class TestCompareFastapiApproaches:
    """Tests for the compare_fastapi_approaches tool."""

    async def test_compares_auth_methods(self) -> None:
        """Should compare authentication methods."""
        result = await compare_fastapi_approaches("auth-methods")
        assert "Authentication" in result
        assert "```python" in result

    async def test_compares_sync_async(self) -> None:
        """Should compare sync vs async."""
        result = await compare_fastapi_approaches("sync-async")
        assert "Async" in result or "async" in result

    async def test_handles_unknown_comparison(self) -> None:
        """Should return available comparisons for unknown topic."""
        result = await compare_fastapi_approaches("unknown-topic")
        assert "Available comparisons" in result
        assert "sync-async" in result


class TestGetFastapiBestPractices:
    """Tests for the get_fastapi_best_practices tool."""

    async def test_gets_security_practices(self) -> None:
        """Should get security best practices."""
        result = await get_fastapi_best_practices("security")
        assert "Best Practices" in result
        assert "security" in result.lower()
        assert BASE_URL in result

    async def test_gets_testing_practices(self) -> None:
        """Should get testing best practices."""
        result = await get_fastapi_best_practices("testing")
        assert "Best Practices" in result
        assert "test" in result.lower()

    async def test_handles_unknown_topic(self) -> None:
        """Should return helpful message for unknown topic."""
        result = await get_fastapi_best_practices("xyznonexistent123")
        assert "No documentation found" in result
        assert "list_fastapi_pages" in result


class TestDecodeHtmlEntities:
    """Tests for the decode_html_entities function."""

    def test_decodes_common_entities(self) -> None:
        """Should decode standard HTML entities."""
        assert decode_html_entities("x &lt; 10 &amp; y &gt; 5") == "x < 10 & y > 5"

    def test_decodes_quote_entities(self) -> None:
        """Should decode quote-related entities."""
        result = decode_html_entities("&quot;hello&quot; &apos;world&apos;")
        assert result == "\"hello\" 'world'"

    def test_removes_paragraph_and_section_marks(self) -> None:
        """Should remove paragraph and section mark entities."""
        assert decode_html_entities("text&para;more&sect;end") == "textmoreend"

    def test_no_entities_unchanged(self) -> None:
        """Should return text unchanged when no entities present."""
        assert decode_html_entities("plain text") == "plain text"


class TestCache:
    """Tests for the TTL cache functions."""

    def test_cache_set_and_get(self) -> None:
        """Should store and retrieve values."""
        _cache_set("http://example.com", "cached content")
        assert _cache_get("http://example.com") == "cached content"

    def test_cache_miss(self) -> None:
        """Should return None for missing keys."""
        assert _cache_get("http://nonexistent.com") is None

    def test_cache_expiry(self) -> None:
        """Should return None for expired entries."""
        import time

        # Manually insert an expired entry (timestamp far in the past)
        _cache["http://expired.com"] = (time.monotonic() - 600.0, "old content")
        assert _cache_get("http://expired.com") is None
        # Expired entry should be evicted
        assert "http://expired.com" not in _cache

    async def test_fetch_url_returns_cached(self) -> None:
        """Should return cached content on second fetch_url call."""
        _cache_set("http://example.com/cached", "cached response")
        result = await fetch_url("http://example.com/cached")
        assert result == "cached response"


class TestKeywordAliases:
    """Tests for the keyword alias mappings."""

    def test_keyword_aliases_has_auth(self) -> None:
        """Should map auth to security."""
        assert _KEYWORD_ALIASES["auth"] == "security"

    def test_keyword_aliases_has_db(self) -> None:
        """Should map db to sql-databases."""
        assert _KEYWORD_ALIASES["db"] == "sql-databases"

    def test_keyword_aliases_has_ws(self) -> None:
        """Should map ws to websockets."""
        assert _KEYWORD_ALIASES["ws"] == "websockets"

    def test_keyword_aliases_has_di(self) -> None:
        """Should map di to dependencies."""
        assert _KEYWORD_ALIASES["di"] == "dependencies"


# ---- Mocked tests for 100% coverage ----


class TestFetchUrlErrors:
    """Tests for fetch_url error handling branches."""

    async def test_timeout_returns_none(self) -> None:
        """Should return None on timeout."""
        with patch("main.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_url("http://example.com/timeout")
            assert result is None

    async def test_generic_http_error_returns_none(self) -> None:
        """Should return None on generic HTTPError."""
        with patch("main.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.HTTPError("connection failed")
            mock_client_cls.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await fetch_url("http://example.com/error")
            assert result is None


class TestFetchSitemapMocked:
    """Tests for fetch_sitemap failure path."""

    async def test_returns_empty_on_fetch_failure(self) -> None:
        """Should return empty list when fetch_url returns None."""
        with patch("main.fetch_url", new_callable=AsyncMock, return_value=None):
            result = await fetch_sitemap()
            assert result == []


class TestSearchSitemapUrls:
    """Tests for _search_sitemap_urls edge cases."""

    async def test_empty_sitemap_returns_empty(self) -> None:
        """Should return empty list when sitemap is empty."""
        with patch("main.fetch_sitemap", new_callable=AsyncMock, return_value=[]):
            result = await _search_sitemap_urls("cors")
            assert result == []

    async def test_alias_fallback(self) -> None:
        """Should use keyword alias when direct search fails."""
        # Use "db" → "sql-databases" alias. "db" is NOT a substring of
        # "sql-databases", so direct search misses and alias branch triggers.
        fake_urls = [
            f"{BASE_URL}/tutorial/sql-databases/",
            f"{BASE_URL}/tutorial/first-steps/",
        ]
        with patch(
            "main.fetch_sitemap", new_callable=AsyncMock, return_value=fake_urls
        ):
            result = await _search_sitemap_urls("db")
            assert len(result) >= 1
            assert any("sql-databases" in path for path in result)


class TestSearchFastapiDocsMocked:
    """Tests for search_fastapi_docs fetch failure."""

    async def test_found_but_cannot_fetch(self) -> None:
        """Should return message when match found but fetch fails."""
        with (
            patch(
                "main._search_sitemap_urls",
                new_callable=AsyncMock,
                return_value=["tutorial/cors"],
            ),
            patch("main.fetch_url", new_callable=AsyncMock, return_value=None),
        ):
            result = await search_fastapi_docs("cors")
            assert "Found" in result
            assert "could not fetch" in result


class TestListFastapiPagesMocked:
    """Tests for list_fastapi_pages failure paths."""

    async def test_empty_sitemap(self) -> None:
        """Should return browse message when sitemap is empty."""
        with patch("main.fetch_sitemap", new_callable=AsyncMock, return_value=[]):
            result = await list_fastapi_pages()
            assert "Could not fetch sitemap" in result
            assert BASE_URL in result

    async def test_skips_empty_categories(self) -> None:
        """Should skip categories with no matching URLs."""
        # Only tutorial URLs — advanced/deployment/how-to/reference will be empty
        fake_urls = [f"{BASE_URL}/tutorial/first-steps/"]
        with patch(
            "main.fetch_sitemap", new_callable=AsyncMock, return_value=fake_urls
        ):
            result = await list_fastapi_pages()
            assert "Tutorial" in result
            assert "Total pages" in result


class TestGetFastapiExampleMocked:
    """Tests for get_fastapi_example failure paths."""

    async def test_fetch_failure(self) -> None:
        """Should return error when fetch_url returns None."""
        with (
            patch(
                "main._search_sitemap_urls",
                new_callable=AsyncMock,
                return_value=["tutorial/cors"],
            ),
            patch("main.fetch_url", new_callable=AsyncMock, return_value=None),
        ):
            result = await get_fastapi_example("cors")
            assert "Could not fetch" in result

    async def test_no_code_blocks(self) -> None:
        """Should return message when page has no code blocks."""
        html_no_code = "<html><body><p>Just text, no code.</p></body></html>"
        with (
            patch(
                "main._search_sitemap_urls",
                new_callable=AsyncMock,
                return_value=["tutorial/cors"],
            ),
            patch("main.fetch_url", new_callable=AsyncMock, return_value=html_no_code),
        ):
            result = await get_fastapi_example("cors")
            assert "No code examples" in result


class TestCompareFastapiApproachesMocked:
    """Tests for compare_fastapi_approaches failure paths."""

    async def test_page_fetch_failure_skipped(self) -> None:
        """Should skip pages that fail to fetch."""
        with patch("main.fetch_url", new_callable=AsyncMock, return_value=None):
            result = await compare_fastapi_approaches("sync-async")
            # Should still return header content even if all pages fail
            assert "Sync vs Async" in result


class TestGetFastapiBestPracticesMocked:
    """Tests for get_fastapi_best_practices failure paths."""

    async def test_empty_sitemap(self) -> None:
        """Should return browse message when sitemap fails."""
        with patch("main.fetch_sitemap", new_callable=AsyncMock, return_value=[]):
            result = await get_fastapi_best_practices("security")
            assert "Could not fetch documentation" in result
            assert BASE_URL in result

    async def test_page_fetch_failure_skipped(self) -> None:
        """Should skip pages that fail to fetch."""
        fake_urls = [f"{BASE_URL}/tutorial/security/"]
        with (
            patch("main.fetch_sitemap", new_callable=AsyncMock, return_value=fake_urls),
            patch("main.fetch_url", new_callable=AsyncMock, return_value=None),
        ):
            result = await get_fastapi_best_practices("security")
            assert "Best Practices" in result
