"""Tests for the FastAPI Docs MCP server (network mocked at the http layer)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from fastapi_docs_mcp import (
    cache,
    content,
    html,
    http,
    markdown,
    server,
    sitemap,
    tools,
)
from fastapi_docs_mcp.config import BASE_URL, DOCS_RAW_BASE, REPO_RAW_ROOT, SITEMAP_URL

# --------------------------------------------------------------------------- #
# Fixtures: canned upstream content, routed by URL.                           #
# --------------------------------------------------------------------------- #

FAKE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <loc>https://fastapi.tiangolo.com/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/first-steps/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/cors/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/security/</loc>
  <loc>https://fastapi.tiangolo.com/tutorial/sql-databases/</loc>
  <loc>https://fastapi.tiangolo.com/advanced/websockets/</loc>
  <loc>https://fastapi.tiangolo.com/some-random-page/</loc>
</urlset>"""

FAKE_CORS_MD = """# CORS (Cross-Origin Resource Sharing) { #cors }

Configure CORS with a [link](https://example.com) and an ![shot](https://x.png).

/// note | Technical Details

You could also import from starlette.

///

/// tip

Be explicit.

///

{* ../../docs_src/cors/tutorial001.py ln[1:3] *}

```console
$ fastapi dev
Started server
lots of logs here
```

```json
{"hello": "world"}
```
"""

FAKE_CORS_PY = """from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
origins = ["http://localhost"]
"""

FAKE_SECURITY_MD = "# Security\n\nUse OAuth2 and JWT for auth.\n"


def _route(url: str) -> str | None:
    if url == SITEMAP_URL:
        return FAKE_SITEMAP
    if url == f"{DOCS_RAW_BASE}/tutorial/cors.md":
        return FAKE_CORS_MD
    if url == f"{REPO_RAW_ROOT}/docs_src/cors/tutorial001.py":
        return FAKE_CORS_PY
    if url == f"{DOCS_RAW_BASE}/tutorial/security.md":
        return FAKE_SECURITY_MD
    return None


@pytest.fixture
def mock_net(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch(url: str) -> str | None:
        return _route(url)

    monkeypatch.setattr(http, "fetch", fake_fetch)


# --------------------------------------------------------------------------- #
# cache                                                                       #
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# http                                                                        #
# --------------------------------------------------------------------------- #


class _FakeStream:
    def __init__(
        self,
        *,
        url: str = f"{BASE_URL}/x",
        chunks: tuple[bytes, ...] = (b"hello",),
        raise_status: Exception | None = None,
        enter_exc: Exception | None = None,
    ) -> None:
        self.url = httpx.URL(url)
        self.encoding = "utf-8"
        self._chunks = chunks
        self._raise_status = raise_status
        self._enter_exc = enter_exc

    async def __aenter__(self) -> _FakeStream:
        if self._enter_exc is not None:
            raise self._enter_exc
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self._raise_status is not None:
            raise self._raise_status

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def _patch_client(monkeypatch: pytest.MonkeyPatch, stream: _FakeStream) -> None:
    class _FakeClient:
        is_closed = False

        def stream(self, _method: str, _url: str) -> _FakeStream:
            return stream

    monkeypatch.setattr(http, "get_client", lambda: _FakeClient())


class TestHttp:
    def test_host_allowed(self) -> None:
        assert http._host_allowed("https://fastapi.tiangolo.com/x")
        assert http._host_allowed("https://raw.githubusercontent.com/y")
        assert not http._host_allowed("https://evil.com/z")

    async def test_download_rejects_disallowed_host(self) -> None:
        assert await http._download("https://evil.com/x") is None

    async def test_download_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, _FakeStream(chunks=(b"abc", b"def")))
        assert await http._download(f"{BASE_URL}/ok") == "abcdef"

    async def test_download_redirect_off_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(url="https://evil.com/redirected"))
        assert await http._download(f"{BASE_URL}/ok") is None

    async def test_download_size_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("fastapi_docs_mcp.http.MAX_DOWNLOAD_BYTES", 4)
        _patch_client(monkeypatch, _FakeStream(chunks=(b"aaaa", b"bbbb")))
        # First chunk (4 bytes) is within cap; second pushes over and is dropped.
        assert await http._download(f"{BASE_URL}/big") == "aaaa"

    async def test_download_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, _FakeStream(enter_exc=httpx.TimeoutException("t")))
        assert await http._download(f"{BASE_URL}/slow") is None

    async def test_download_status_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        err = httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", f"{BASE_URL}/x"),
            response=httpx.Response(404),
        )
        _patch_client(monkeypatch, _FakeStream(raise_status=err))
        assert await http._download(f"{BASE_URL}/missing") is None

    async def test_download_generic_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(enter_exc=httpx.HTTPError("boom")))
        assert await http._download(f"{BASE_URL}/err") is None

    async def test_fetch_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = 0

        async def fake_download(_url: str) -> str:
            nonlocal calls
            calls += 1
            return "payload"

        monkeypatch.setattr(http, "_download", fake_download)
        assert await http.fetch(f"{BASE_URL}/c") == "payload"
        assert await http.fetch(f"{BASE_URL}/c") == "payload"
        assert calls == 1

    async def test_get_client_singleton(self) -> None:
        c1 = http.get_client()
        c2 = http.get_client()
        assert c1 is c2
        await http.aclose()
        assert http._client is None


# --------------------------------------------------------------------------- #
# sitemap                                                                      #
# --------------------------------------------------------------------------- #


class TestSitemap:
    async def test_fetch_sitemap(self, mock_net: None) -> None:
        urls = await sitemap.fetch_sitemap()
        assert f"{BASE_URL}/tutorial/cors/" in urls

    async def test_fetch_sitemap_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def none(_: str) -> None:
            return None

        monkeypatch.setattr(http, "fetch", none)
        assert await sitemap.fetch_sitemap() == []

    async def test_search_direct(self, mock_net: None) -> None:
        assert "tutorial/cors" in await sitemap.search_sitemap_urls("cors")

    async def test_search_alias(self, mock_net: None) -> None:
        # "auth" is not a substring of any URL → alias maps to "security".
        result = await sitemap.search_sitemap_urls("auth")
        assert any("security" in p for p in result)

    async def test_search_empty_sitemap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def none(_: str) -> None:
            return None

        monkeypatch.setattr(http, "fetch", none)
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


# --------------------------------------------------------------------------- #
# markdown                                                                     #
# --------------------------------------------------------------------------- #


class TestMarkdown:
    def test_url_candidates(self) -> None:
        assert markdown.md_url_candidates("") == [f"{DOCS_RAW_BASE}/index.md"]
        assert markdown.md_url_candidates("tutorial/cors") == [
            f"{DOCS_RAW_BASE}/tutorial/cors.md",
            f"{DOCS_RAW_BASE}/tutorial/cors/index.md",
        ]

    def test_include_url(self) -> None:
        assert markdown._include_url("../../docs_src/cors/t.py") == (
            f"{REPO_RAW_ROOT}/docs_src/cors/t.py"
        )
        assert markdown._include_url("no/match/here.py") is None

    def test_slice_lines(self) -> None:
        code = "a\nb\nc\nd"
        assert markdown._slice_lines(code, "ln[2:3]") == "b\nc"
        assert markdown._slice_lines(code, "") == code

    async def test_resolve_includes(self, mock_net: None) -> None:
        out = await markdown.resolve_includes(
            "{* ../../docs_src/cors/tutorial001.py ln[1:2] *}"
        )
        assert "```python" in out
        assert "from fastapi import FastAPI" in out
        assert "origins" not in out  # ln[1:2] kept only the first two lines

    async def test_resolve_includes_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def none(_: str) -> None:
            return None

        monkeypatch.setattr(http, "fetch", none)
        out = await markdown.resolve_includes("{* ../../docs_src/x/y.py *}")
        assert "unavailable" in out

    async def test_resolve_includes_noop(self) -> None:
        assert await markdown.resolve_includes("plain text") == "plain text"

    def test_clean_mkdocs(self) -> None:
        out = markdown.clean_mkdocs(FAKE_CORS_MD)
        assert "{ #cors }" not in out  # anchor stripped
        assert "**Technical Details**" in out  # admonition w/ title
        assert "**Tip**" in out  # admonition w/o title
        assert "https://example.com" not in out  # link URL dropped
        assert "link" in out  # link text kept
        assert "![shot]" not in out  # image dropped
        assert "$ fastapi dev" in out  # command kept
        assert "lots of logs here" not in out  # console output dropped

    def test_clean_mkdocs_caps_other_blocks(self) -> None:
        big = "```json\n" + ("x" * 2000) + "\n```"
        out = markdown.clean_mkdocs(big)
        assert "truncated" in out
        assert len(out) < 1000

    def test_extract_python_blocks(self) -> None:
        md = "```python\nfrom fastapi import FastAPI\napp = FastAPI()\n```\nprose"
        blocks = markdown.extract_python_blocks(md)
        assert len(blocks) == 1
        assert "FastAPI" in blocks[0]

    def test_truncate_short(self) -> None:
        assert markdown.truncate_content("hi", 100) == "hi"

    def test_truncate_long(self) -> None:
        out = markdown.truncate_content("A" * 200, 100)
        assert "truncated" in out.lower()

    def test_truncate_paragraph_break(self) -> None:
        text = "First para.\n\n" + "B" * 50 + "\n\nThird."
        out = markdown.truncate_content(text, 80)
        assert out.startswith("First para.")

    async def test_to_clean_markdown(self, mock_net: None) -> None:
        out = await markdown.to_clean_markdown("tutorial/cors")
        assert "CORS" in out
        assert "from fastapi import FastAPI" in out

    async def test_to_clean_markdown_missing(self, mock_net: None) -> None:
        assert await markdown.to_clean_markdown("does/not/exist") is None


# --------------------------------------------------------------------------- #
# html fallback                                                                #
# --------------------------------------------------------------------------- #


class TestHtml:
    def test_extract_text(self) -> None:
        out = html.extract_text(
            "<nav>x</nav><article><p>Hello <b>world</b></p></article>"
        )
        assert "Hello" in out and "world" in out
        assert "<p>" not in out

    def test_removes_scripts(self) -> None:
        out = html.extract_text("<p>Keep</p><script>evil()</script>")
        assert "Keep" in out and "evil" not in out

    def test_decode_entities(self) -> None:
        assert html.decode_html_entities("a &lt; b &amp; c") == "a < b & c"

    def test_extract_code_blocks(self) -> None:
        out = html.extract_code_blocks(
            "<pre><code>def hello():\n    return 1 &lt; 2</code></pre>"
        )
        assert out and "def hello" in out[0]
        assert "<" in out[0]


# --------------------------------------------------------------------------- #
# content seam                                                                 #
# --------------------------------------------------------------------------- #


class TestContent:
    async def test_text_markdown_path(self, mock_net: None) -> None:
        out = await content.get_page_text("tutorial/cors")
        assert out is not None and "CORS" in out

    async def test_text_html_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fetch(url: str) -> str | None:
            if url.startswith(BASE_URL):  # live site → HTML
                return "<article><p>Fallback body</p></article>"
            return None  # markdown source missing

        monkeypatch.setattr(http, "fetch", fetch)
        out = await content.get_page_text("tutorial/cors")
        assert out is not None and "Fallback body" in out

    async def test_text_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def none(_: str) -> None:
            return None

        monkeypatch.setattr(http, "fetch", none)
        assert await content.get_page_text("x") is None

    async def test_code_markdown_path(self, mock_net: None) -> None:
        blocks = await content.get_page_code("tutorial/cors")
        assert blocks and "FastAPI" in blocks[0]

    async def test_code_html_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fetch(url: str) -> str | None:
            if url.startswith(BASE_URL):
                return "<pre><code>print('hi there from fallback')</code></pre>"
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        blocks = await content.get_page_code("tutorial/cors")
        assert blocks and "fallback" in blocks[0]


# --------------------------------------------------------------------------- #
# tools                                                                        #
# --------------------------------------------------------------------------- #


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

    async def test_search(self, mock_net: None) -> None:
        out = await tools.search_fastapi_docs("cors")
        assert "CORS" in out

    async def test_search_alias(self, mock_net: None) -> None:
        out = await tools.search_fastapi_docs("auth")
        assert "Security" in out or "security" in out.lower()

    async def test_search_no_results(self, mock_net: None) -> None:
        out = await tools.search_fastapi_docs("zzzznope")
        assert "No results" in out

    async def test_search_fetch_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fetch(url: str) -> str | None:
            return FAKE_SITEMAP if url == SITEMAP_URL else None

        monkeypatch.setattr(http, "fetch", fetch)
        out = await tools.search_fastapi_docs("cors")
        assert "could not fetch" in out.lower()

    async def test_list_pages(self, mock_net: None) -> None:
        out = await tools.list_fastapi_pages()
        assert "Tutorial" in out and "Total pages" in out

    async def test_list_pages_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def none(_: str) -> None:
            return None

        monkeypatch.setattr(http, "fetch", none)
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

    async def test_best_practices_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def none(_: str) -> None:
            return None

        monkeypatch.setattr(http, "fetch", none)
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


# --------------------------------------------------------------------------- #
# server                                                                       #
# --------------------------------------------------------------------------- #


class TestServer:
    async def test_tools_registered(self) -> None:
        registered = {tool.name for tool in await server.mcp.list_tools()}
        assert "get_fastapi_docs" in registered
        assert len(registered) == 6

    async def test_lifespan_closes_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed = False

        async def fake_aclose() -> None:
            nonlocal closed
            closed = True

        monkeypatch.setattr(http, "aclose", fake_aclose)
        async with server._lifespan(server.mcp):
            pass
        assert closed


# --------------------------------------------------------------------------- #
# integration (opt-in: `uv run pytest -m integration`)                         #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
class TestLive:
    async def test_live_docs(self) -> None:
        out = await tools.get_fastapi_docs("tutorial/first-steps")
        assert "FastAPI" in out

    async def test_live_sitemap(self) -> None:
        urls = await sitemap.fetch_sitemap()
        assert urls and all(u.startswith(BASE_URL) for u in urls)
