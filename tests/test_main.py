"""Tests for FastAPI Docs MCP Server."""

from main import (
    BASE_URL,
    categorize_urls,
    compare_fastapi_approaches,
    extract_code_blocks,
    extract_text_from_html,
    fetch_sitemap,
    fetch_url,
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
        result = await get_fastapi_docs.fn("tutorial/first-steps")
        assert "FastAPI" in result
        assert "tutorial/first-steps" in result

    async def test_handles_invalid_page(self) -> None:
        """Should return helpful message for invalid paths."""
        result = await get_fastapi_docs.fn("nonexistent/page")
        assert "Could not find" in result or "list_fastapi_pages" in result


class TestSearchFastapiDocs:
    """Tests for the search_fastapi_docs tool."""

    async def test_finds_direct_match(self) -> None:
        """Should find pages matching the search term."""
        result = await search_fastapi_docs.fn("cors")
        assert "cors" in result.lower()
        assert BASE_URL in result

    async def test_uses_keyword_aliases(self) -> None:
        """Should use keyword aliases for common terms."""
        result = await search_fastapi_docs.fn("auth")
        assert "security" in result.lower()

    async def test_handles_no_results(self) -> None:
        """Should return helpful message when no results found."""
        result = await search_fastapi_docs.fn("xyznonexistent123")
        assert "No results" in result or "list_fastapi_pages" in result


class TestListFastapiPages:
    """Tests for the list_fastapi_pages tool."""

    async def test_lists_pages(self) -> None:
        """Should list documentation pages."""
        result = await list_fastapi_pages.fn()
        assert "Tutorial" in result
        assert "Advanced" in result
        assert "Total pages" in result

    async def test_includes_paths(self) -> None:
        """Should include actual page paths."""
        result = await list_fastapi_pages.fn()
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
        result = await get_fastapi_example.fn("cors")
        assert "```python" in result
        assert "CORS" in result or "cors" in result.lower()

    async def test_gets_dependencies_example(self) -> None:
        """Should get code examples for dependencies."""
        result = await get_fastapi_example.fn("dependencies")
        assert "```python" in result
        assert "Example" in result

    async def test_handles_unknown_topic(self) -> None:
        """Should return helpful message for unknown topics."""
        result = await get_fastapi_example.fn("xyznonexistent")
        assert "No examples found" in result or "Try:" in result


class TestCompareFastapiApproaches:
    """Tests for the compare_fastapi_approaches tool."""

    async def test_compares_auth_methods(self) -> None:
        """Should compare authentication methods."""
        result = await compare_fastapi_approaches.fn("auth-methods")
        assert "Authentication" in result
        assert "```python" in result

    async def test_compares_sync_async(self) -> None:
        """Should compare sync vs async."""
        result = await compare_fastapi_approaches.fn("sync-async")
        assert "Async" in result or "async" in result

    async def test_handles_unknown_comparison(self) -> None:
        """Should return available comparisons for unknown topic."""
        result = await compare_fastapi_approaches.fn("unknown-topic")
        assert "Available comparisons" in result
        assert "sync-async" in result
