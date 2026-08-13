"""Tests for the content acquisition seam: markdown-preferred, HTML fallback.

The highest-value tests here cover the confirmed-absent-vs-unreachable
distinction (see ``content.py``'s module docstring and ``docs/DESIGN.md``
§2.5/§5.3): a page that genuinely doesn't exist returns ``None`` (soft), but
a page neither source could even be checked for raises ``ToolError`` — that
split is what keeps the markdown/HTML fallback seam's resilience guarantee
honest under a transient outage.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from fastapi_docs_mcp import content, http
from fastapi_docs_mcp.config import BASE_URL, DOCS_RAW_BASE


def _is_markdown_url(url: str) -> bool:
    return url.startswith(DOCS_RAW_BASE)


def _is_html_url(url: str) -> bool:
    return url.startswith(BASE_URL)


class TestGetPageText:
    async def test_markdown_path(self, mock_net: None) -> None:
        out = await content.get_page_text("tutorial/cors")
        assert out is not None and "CORS" in out

    async def test_confirmed_absent_markdown_html_fallback_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(url: str) -> str | None:
            if _is_html_url(url):
                return "<article><p>Fallback body</p></article>"
            return None  # markdown source confirmed absent

        monkeypatch.setattr(http, "fetch", fetch)
        out = await content.get_page_text("tutorial/cors")
        assert out is not None and "Fallback body" in out

    async def test_confirmed_absent_both_sources_returns_none(
        self, none_net: None
    ) -> None:
        assert await content.get_page_text("x") is None

    async def test_markdown_transient_html_succeeds_returns_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(url: str) -> str | None:
            if _is_markdown_url(url):
                raise http.UpstreamError("simulated timeout")
            if _is_html_url(url):
                return "<article><p>Rescued by fallback</p></article>"
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        out = await content.get_page_text("tutorial/cors")
        assert out is not None and "Rescued by fallback" in out

    async def test_both_sources_unreachable_raises_tool_error(
        self, unreachable_net: None
    ) -> None:
        with pytest.raises(ToolError):
            await content.get_page_text("tutorial/cors")

    async def test_markdown_confirmed_absent_html_unreachable_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Markdown gave a confirmed answer (absent); the HTML side's transient
        # failure is moot — a partial confirmation still resolves softly.
        async def fetch(url: str) -> str | None:
            if _is_markdown_url(url):
                return None
            if _is_html_url(url):
                raise http.UpstreamError("simulated timeout")
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        assert await content.get_page_text("tutorial/cors") is None

    async def test_markdown_unreachable_html_confirmed_absent_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(url: str) -> str | None:
            if _is_markdown_url(url):
                raise http.UpstreamError("simulated timeout")
            return None  # HTML confirms absence

        monkeypatch.setattr(http, "fetch", fetch)
        assert await content.get_page_text("tutorial/cors") is None


class TestGetPageCode:
    async def test_markdown_path(self, mock_net: None) -> None:
        blocks = await content.get_page_code("tutorial/cors")
        assert blocks and "FastAPI" in blocks[0]

    async def test_confirmed_absent_markdown_html_fallback_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(url: str) -> str | None:
            if _is_html_url(url):
                return "<pre><code>print('hi there from fallback')</code></pre>"
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        blocks = await content.get_page_code("tutorial/cors")
        assert blocks and "fallback" in blocks[0]

    async def test_confirmed_absent_both_sources_returns_empty_list(
        self, none_net: None
    ) -> None:
        assert await content.get_page_code("x") == []

    async def test_both_sources_unreachable_raises_tool_error(
        self, unreachable_net: None
    ) -> None:
        with pytest.raises(ToolError):
            await content.get_page_code("tutorial/cors")
