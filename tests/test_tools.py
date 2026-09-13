"""Tests for the six MCP tools — thin orchestration over discovery + content."""

from __future__ import annotations

import asyncio
import time

import pytest
from fastmcp.exceptions import ToolError

from fastapi_docs_mcp import content, http, tools
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

    async def test_get_docs_sanitizes_embedded_newline(self, mock_net: None) -> None:
        # Regression test for the CRLF-survival gap: an embedded \r\n must not
        # reach the constructed URL, and the injected text must not land on
        # its own line (the actual log-injection/header-injection primitive).
        out = await tools.get_fastapi_docs("tutorial/cors\r\nX-Injected: evil")
        assert "\r" not in out
        assert "X-Injected: evil" not in out.splitlines()

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

    async def test_compare_fetches_pages_concurrently(
        self, mock_net: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression test: pages must be fetched concurrently, not one at a
        # time. "tutorial" hits the dynamic-fallback branch with 3 matching
        # pages (see FAKE_SITEMAP); each fetch is delayed, so a sequential
        # implementation (2 awaits/page) would take >= 6x the delay.
        delay = 0.05

        async def slow_text(path: str, max_length: int | None = None) -> str:
            await asyncio.sleep(delay)
            return f"# {path}\n\nSome text."

        async def slow_code(path: str) -> list[str]:
            await asyncio.sleep(delay)
            return []

        monkeypatch.setattr(content, "get_page_text", slow_text)
        monkeypatch.setattr(content, "get_page_code", slow_code)

        start = time.monotonic()
        out = await tools.compare_fastapi_approaches("tutorial")
        elapsed = time.monotonic() - start

        assert elapsed < delay * 3
        assert out.count("Some text") == 3

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

    async def test_best_practices_fetches_pages_concurrently(
        self, mock_net: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "tutorial" matches 3+ pages in FAKE_SITEMAP (capped to the top 3).
        delay = 0.05

        async def slow_text(path: str, max_length: int | None = None) -> str:
            await asyncio.sleep(delay)
            return f"# {path}\n\nSome text."

        monkeypatch.setattr(content, "get_page_text", slow_text)

        start = time.monotonic()
        out = await tools.get_fastapi_best_practices("tutorial")
        elapsed = time.monotonic() - start

        assert elapsed < delay * 3
        assert out.count("Some text") == 3

    def test_clean_path(self) -> None:
        assert tools._clean_path("/tutorial/cors/") == "tutorial/cors"
        assert tools._clean_path("../../etc/passwd") == "etc/passwd"

    def test_clean_arg_strips_all_control_chars(self) -> None:
        # Regression test: the control-char regex used to gap around tab/LF/CR
        # (0x09, 0x0A, 0x0D), letting them survive into a constructed URL --
        # an input-validation gap even though downstream layers (httpx's URL
        # parsing, FastMCP's error masking) already prevented it from being
        # exploitable. Covers the full C0 range (0x00-0x1F) + DEL (0x7F).
        raw = "".join(chr(c) for c in range(0x00, 0x20)) + "\x7f"
        cleaned = tools._clean_arg(f"safe{raw}text")
        assert cleaned == "safetext"

    def test_clean_path_strips_embedded_newline_and_cr(self) -> None:
        injected = "tutorial/cors\r\nX-Injected: evil"
        cleaned = tools._clean_path(injected)
        assert "\r" not in cleaned
        assert "\n" not in cleaned

    def test_cap_code(self) -> None:
        capped = tools._cap_code("\n".join(str(i) for i in range(40)), max_lines=5)
        assert capped.endswith("# ...")
