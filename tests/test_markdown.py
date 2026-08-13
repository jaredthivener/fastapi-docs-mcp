"""Tests for the markdown pipeline: fetch, include resolution, MkDocs cleanup."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fastapi_docs_mcp import http, markdown
from fastapi_docs_mcp.config import DOCS_RAW_BASE, MAX_INCLUDES, REPO_RAW_ROOT

from .fixtures import FAKE_CORS_MD


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

    async def test_fetch_markdown_confirmed_absent(self, none_net: None) -> None:
        assert await markdown.fetch_markdown("does/not/exist") is None

    async def test_fetch_markdown_tries_next_candidate_after_transient_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # First candidate (tutorial/cors.md) times out; the section-index
        # fallback (tutorial/cors/index.md) should still be tried and win.
        first_url = f"{DOCS_RAW_BASE}/tutorial/cors.md"
        second_url = f"{DOCS_RAW_BASE}/tutorial/cors/index.md"

        async def fetch(url: str) -> str | None:
            if url == first_url:
                raise http.UpstreamError("flaky")
            if url == second_url:
                return "# Cors index"
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        assert await markdown.fetch_markdown("tutorial/cors") == "# Cors index"

    async def test_fetch_markdown_raises_when_all_candidates_unreachable(
        self, unreachable_net: None
    ) -> None:
        with pytest.raises(http.UpstreamError):
            await markdown.fetch_markdown("tutorial/cors")

    async def test_resolve_includes(self, mock_net: None) -> None:
        out = await markdown.resolve_includes(
            "{* ../../docs_src/cors/tutorial001.py ln[1:2] *}"
        )
        assert "```python" in out
        assert "from fastapi import FastAPI" in out
        assert "origins" not in out  # ln[1:2] kept only the first two lines

    async def test_resolve_includes_confirmed_absent(self, none_net: None) -> None:
        out = await markdown.resolve_includes("{* ../../docs_src/x/y.py *}")
        assert "unavailable" in out

    async def test_resolve_includes_swallows_transient_error(
        self, unreachable_net: None
    ) -> None:
        # An include is supplementary: a transient failure degrades to the
        # same placeholder as a confirmed-absent include, not a raised error —
        # unlike the page-level fetches in content.py.
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
        assert out is not None
        assert "CORS" in out
        assert "from fastapi import FastAPI" in out

    async def test_to_clean_markdown_confirmed_absent(self, none_net: None) -> None:
        assert await markdown.to_clean_markdown("does/not/exist") is None

    async def test_to_clean_markdown_propagates_upstream_error(
        self, unreachable_net: None
    ) -> None:
        with pytest.raises(http.UpstreamError):
            await markdown.to_clean_markdown("tutorial/cors")


# --------------------------------------------------------------------------- #
# Property-based tests.                                                       #
#                                                                              #
# clean_mkdocs/_split_blocks/resolve_includes are hand-written parsers over   #
# untrusted upstream text — exactly the surface most likely to hit an input   #
# shape the example-based tests above didn't anticipate (unbalanced fences,   #
# nested backticks, unicode). The include-directive syntax has already        #
# changed once upstream ({!...!} -> {* *}), so these assert invariants that   #
# must hold for arbitrary input, rather than specific outputs.                #
# --------------------------------------------------------------------------- #

# Bias toward markdown-ish characters (fences, directive braces, unicode)
# rather than pure noise, so Hypothesis spends its budget near the shapes
# that actually appear in upstream content.
_markdown_ish_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po"),
        whitelist_characters="`{}*!#/\n$>|[]()äü中",
    ),
    max_size=2000,
)


class TestMarkdownProperties:
    @given(_markdown_ish_text)
    @settings(max_examples=200)
    def test_clean_mkdocs_never_raises(self, text: str) -> None:
        markdown.clean_mkdocs(text)

    @given(_markdown_ish_text)
    @settings(max_examples=200)
    def test_split_blocks_never_manufactures_content(self, text: str) -> None:
        blocks = markdown._split_blocks(text)
        assert sum(len(content) for _, content in blocks) <= len(text)

    @given(st.text(max_size=5000), st.integers(min_value=0, max_value=2000))
    @settings(max_examples=200)
    def test_truncate_content_bounds_length(self, text: str, max_length: int) -> None:
        out = markdown.truncate_content(text, max_length)
        if len(text) <= max_length:
            assert out == text
        else:
            # Bounded by max_length plus the fixed truncation-notice suffix.
            suffix = "\n\n... [Content truncated. Visit the URL for full content.]"
            assert len(out) <= max_length + len(suffix)

    @given(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz/_.", min_size=1, max_size=20),
            min_size=0,
            max_size=40,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_resolve_includes_never_exceeds_max_includes(
        self, paths: list[str]
    ) -> None:
        # However many include directives a page contains, resolve_includes
        # must only ever fetch MAX_INCLUDES of them (config.py's cap on a
        # single page's fan-out of upstream docs_src fetches — DESIGN.md §4.2).
        md = "\n".join(f"{{* ../../docs_src/{p}.py *}}" for p in paths)
        calls = 0

        async def fake_fetch(_url: str) -> str | None:
            nonlocal calls
            calls += 1
            return None

        async def run() -> None:
            with patch.object(markdown.http, "fetch", fake_fetch):
                await markdown.resolve_includes(md)

        asyncio.run(run())
        assert calls <= MAX_INCLUDES

    @given(_markdown_ish_text)
    @settings(max_examples=100)
    def test_extract_python_blocks_never_raises(self, text: str) -> None:
        markdown.extract_python_blocks(text)
