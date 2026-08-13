"""Tests for the six MCP tools — thin orchestration over discovery + content."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from fastapi_docs_mcp import http, tools
from fastapi_docs_mcp.config import SITEMAP_URL

from .fixtures import FAKE_SITEMAP


class TestTools:
    async def test_get_docs(self, mock_net: None) -> None:
        out = await tools.get_fastapi_docs("tutorial/cors")
        assert "CORS" in out and "tutorial/cors" in out

    async def test_get_docs_not_found(self, mock_net: None) -> None:
        out = await tools.get_fastapi_docs("nope/nope")
        assert "Could not find" in out

    async def test_get_docs_sanitizes_path(self, mock_net: None) -> None:
        # Traversal + control chars are stripped before building the URL.
        out = await tools.get_fastapi_docs("../../tutorial/cors\x00")
        assert "tutorial/cors" in out
        assert ".." not in out.splitlines()[0]

    async def test_get_docs_unreachable_raises_tool_error(
        self, unreachable_net: None
    ) -> None:
        # Every upstream source failing transiently must surface as an MCP
        # tool execution error (isError: true), not a false "not found".
        with pytest.raises(ToolError):
            await tools.get_fastapi_docs("tutorial/cors")

    async def test_search(self, mock_net: None) -> None:
        out = await tools.search_fastapi_docs("cors")
        assert "CORS" in out

    async def test_search_alias(self, mock_net: None) -> None:
        out = await tools.search_fastapi_docs("auth")
        assert "Security" in out or "security" in out.lower()

    async def test_search_no_results(self, mock_net: None) -> None:
        out = await tools.search_fastapi_docs("zzzznope")
        assert "No results" in out

    async def test_search_content_confirmed_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(url: str) -> str | None:
            return FAKE_SITEMAP if url == SITEMAP_URL else None

        monkeypatch.setattr(http, "fetch", fetch)
        out = await tools.search_fastapi_docs("cors")
        assert "could not fetch" in out.lower()

    async def test_list_pages(self, mock_net: None) -> None:
        out = await tools.list_fastapi_pages()
        assert "Tutorial" in out and "Total pages" in out

    async def test_list_pages_sitemap_confirmed_absent(self, none_net: None) -> None:
        out = await tools.list_fastapi_pages()
        assert "Could not fetch sitemap" in out

    async def test_example(self, mock_net: None) -> None:
        out = await tools.get_fastapi_example("cors")
        assert "```python" in out and "FastAPI" in out

    async def test_example_unknown(self, mock_net: None) -> None:
        out = await tools.get_fastapi_example("zzzznope")
        assert "No examples found" in out

    async def test_example_no_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fetch(url: str) -> str | None:
            if url == SITEMAP_URL:
                return FAKE_SITEMAP
            if url.endswith("security.md"):
                return "# Security\n\nProse only, no code.\n"
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        out = await tools.get_fastapi_example("security")
        assert "No code examples" in out

    async def test_compare_curated(self, mock_net: None) -> None:
        out = await tools.compare_fastapi_approaches("auth-methods")
        assert "Authentication Methods" in out

    async def test_compare_alias_and_selfheal(self, mock_net: None) -> None:
        # "security" aliases to auth-methods; only tutorial/security exists in the
        # fake sitemap, so the other configured pages are self-healed away.
        out = await tools.compare_fastapi_approaches("security")
        assert "Authentication Methods" in out
        assert "Security" in out

    async def test_compare_dynamic_fallback(self, mock_net: None) -> None:
        out = await tools.compare_fastapi_approaches("cors")
        assert "Cors Approaches" in out

    async def test_compare_help(self, mock_net: None) -> None:
        out = await tools.compare_fastapi_approaches("zzzznope")
        assert "Available comparisons" in out

    async def test_best_practices(self, mock_net: None) -> None:
        out = await tools.get_fastapi_best_practices("security")
        assert "Best Practices" in out and "Security" in out

    async def test_best_practices_sitemap_confirmed_absent(
        self, none_net: None
    ) -> None:
        out = await tools.get_fastapi_best_practices("security")
        assert "Could not fetch documentation" in out

    async def test_best_practices_no_match(self, mock_net: None) -> None:
        out = await tools.get_fastapi_best_practices("zzzznope")
        assert "No documentation found" in out

    def test_clean_path(self) -> None:
        assert tools._clean_path("/tutorial/cors/") == "tutorial/cors"
        assert tools._clean_path("../../etc/passwd") == "etc/passwd"

    def test_cap_code(self) -> None:
        capped = tools._cap_code("\n".join(str(i) for i in range(40)), max_lines=5)
        assert capped.endswith("# ...")
