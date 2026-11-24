"""Tests for the markdown pipeline: fetch, include resolution, MkDocs cleanup."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fastapi_docs_mcp import http, markdown
from fastapi_docs_mcp.config import (
    DOCS_RAW_BASE,
    MAX_INCLUDES,
    MIN_CODE_BLOCK_CHARS,
    REPO_RAW_ROOT,
    TRUNCATE_BREAK_RATIO,
)

from .fixtures import FAKE_CORS_MD

# truncate_content scenarios are expressed relative to the configured ratio, so
# retuning it moves the cases with it instead of silently invalidating them.
_MAX = 100
_EDGE = int(_MAX * TRUNCATE_BREAK_RATIO)  # a break here is NOT past the threshold
_PAST = _EDGE + 5  # a break here is


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

    async def test_resolve_includes_skips_fetch_for_non_docs_src_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A ref with no docs_src/ anchor can't be mapped to a raw URL, so it
        # degrades to the placeholder without touching the network.
        calls: list[str] = []

        async def fetch(url: str) -> str | None:
            calls.append(url)
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        out = await markdown.resolve_includes("{* ../../elsewhere/y.py *}")
        assert "(example unavailable: ../../elsewhere/y.py)" in out
        assert calls == []

    async def test_resolve_includes_keeps_surrounding_text_and_indentation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(url: str) -> str | None:
            if url == f"{REPO_RAW_ROOT}/docs_src/x/y.py":
                return "def f():\n    return 1\n"
            return None

        monkeypatch.setattr(http, "fetch", fetch)
        md = "Intro\n\n{* ../../docs_src/x/y.py ln[2:2] *}\n\nOutro"
        out = await markdown.resolve_includes(md)
        # Text either side survives intact, and the sliced line keeps its
        # leading indentation (it is code: stripping it would change meaning).
        assert out == "Intro\n\n```python\n    return 1\n```\n\nOutro"

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

    @pytest.mark.parametrize(
        ("text", "kept"),
        [
            pytest.param(
                "A" * _PAST + "\n\n" + "B" * 50,
                "A" * _PAST,
                id="break-past-threshold-backs-up-to-it",
            ),
            pytest.param(
                "A" * 10 + "\n\n" + "B" * 200,
                ("A" * 10 + "\n\n" + "B" * 200)[:_MAX],
                id="early-break-ignored",
            ),
            pytest.param(
                "A" * 10 + "\n\n" + "B" * (_PAST - 12) + "\n\n" + "C" * 50,
                ("A" * 10 + "\n\n" + "B" * (_PAST - 12) + "\n\n" + "C" * 50)[:_PAST],
                id="last-break-wins",
            ),
            pytest.param(
                "A" * _EDGE + "\n\n" + "B" * 50,
                ("A" * _EDGE + "\n\n" + "B" * 50)[:_MAX],
                id="break-exactly-at-threshold-ignored",
            ),
        ],
    )
    def test_truncate_cut_point(self, text: str, kept: str) -> None:
        assert markdown.truncate_content(text, _MAX) == kept + markdown.TRUNCATION_NOTE

    def test_truncate_content_exactly_at_limit_is_untouched(self) -> None:
        assert markdown.truncate_content("A" * _MAX, _MAX) == "A" * _MAX

    @pytest.mark.parametrize(
        ("length", "kept"),
        [(MIN_CODE_BLOCK_CHARS, False), (MIN_CODE_BLOCK_CHARS + 1, True)],
        ids=["at-minimum-dropped", "one-over-kept"],
    )
    def test_extract_python_blocks_minimum_length(
        self, length: int, kept: bool
    ) -> None:
        code = "c" * length
        out = markdown.extract_python_blocks(f"```python\n{code}\n```")
        assert out == ([code] if kept else [])

    def test_extract_python_blocks_strips_html_tags(self) -> None:
        md = "```python\n<span>x_value = 1</span>\ny_value = 2\n```"
        assert markdown.extract_python_blocks(md) == ["x_value = 1\ny_value = 2"]

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
