"""Tests for the lean HTML→text/code fallback extractor."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fastapi_docs_mcp import html
from fastapi_docs_mcp.config import BARE_CODE_MIN_CHARS, MIN_CODE_BLOCK_CHARS


def _multiline(n: int) -> str:
    """A two-line code string of exactly ``n`` chars (``n`` >= 3)."""
    return "a\n" + "b" * (n - 2)


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

    def test_decode_entities_beyond_the_original_hand_rolled_table(self) -> None:
        # stdlib html.unescape covers the full HTML5 entity set, not just the
        # handful the old hand-rolled table listed.
        assert html.decode_html_entities("&copy; caf&eacute; &#8482;") == ("© café ™")

    def test_decode_entities_drops_heading_anchor_glyphs(self) -> None:
        # &para;/&sect; are FastAPI's heading-permalink glyphs -- noise for an
        # LLM, dropped rather than decoded to ¶/§.
        assert html.decode_html_entities("Security&para;&sect;") == "Security"

    def test_extract_code_blocks(self) -> None:
        out = html.extract_code_blocks(
            "<pre><code>def hello():\n    return 1 &lt; 2</code></pre>"
        )
        assert out and "def hello" in out[0]
        assert "<" in out[0]

    def test_extract_code_blocks_keeps_long_bare_code_only(self) -> None:
        # A bare <code> (no <pre>) is kept only if it is multi-line AND longer
        # than 50 chars; inline snippets like <code>pip</code> are prose.
        long_block = "\n".join(f"value_{i} = {i}" for i in range(8))
        assert len(long_block) > 50
        out = html.extract_code_blocks(
            f"<p>Run <code>pip</code> then:</p><code>{long_block}</code>"
        )
        assert out == [long_block]

    @pytest.mark.parametrize(
        ("block", "kept"),
        [
            pytest.param(_multiline(BARE_CODE_MIN_CHARS), False, id="at-minimum"),
            pytest.param(_multiline(BARE_CODE_MIN_CHARS + 1), True, id="one-over"),
            pytest.param("b" * (BARE_CODE_MIN_CHARS + 10), False, id="long-one-liner"),
            pytest.param(
                _multiline(MIN_CODE_BLOCK_CHARS + 1), False, id="short-multiline"
            ),
        ],
    )
    def test_extract_code_blocks_bare_code_filter(self, block: str, kept: bool) -> None:
        out = html.extract_code_blocks(f"<code>{block}</code>")
        assert out == ([block] if kept else [])

    @pytest.mark.parametrize(
        ("length", "kept"),
        [(MIN_CODE_BLOCK_CHARS, False), (MIN_CODE_BLOCK_CHARS + 1, True)],
        ids=["at-minimum-dropped", "one-over-kept"],
    )
    def test_extract_code_blocks_minimum_length(self, length: int, kept: bool) -> None:
        block = "c" * length
        out = html.extract_code_blocks(f"<pre><code>{block}</code></pre>")
        assert out == ([block] if kept else [])

    def test_extract_code_blocks_does_not_duplicate_pre_code_blocks(self) -> None:
        # Regression: a multi-line pre/code block over BARE_CODE_MIN_CHARS used
        # to match both _PRE_CODE_RE and the bare-<code> pass, and come back twice.
        block = _multiline(BARE_CODE_MIN_CHARS + 10)
        assert html.extract_code_blocks(f"<pre><code>{block}</code></pre>") == [block]

    def test_extract_code_blocks_pre_blocks_then_bare_blocks_in_order(self) -> None:
        # A page with both kinds yields each exactly once, <pre> blocks first.
        pre = _multiline(BARE_CODE_MIN_CHARS + 10).replace("a\n", "p\n", 1)
        bare = _multiline(BARE_CODE_MIN_CHARS + 20)
        out = html.extract_code_blocks(
            f"<code>{bare}</code><pre><code>{pre}</code></pre>"
        )
        assert out == [pre, bare]

    def test_extract_code_blocks_strips_highlighting_tags(self) -> None:
        lines = [f"line{i} = {i}" for i in range(5)]
        marked_up = "\n".join(f"<span>{ln}</span>" for ln in lines)
        assert html.extract_code_blocks(f"<code>{marked_up}</code>") == [
            "\n".join(lines)
        ]


# --------------------------------------------------------------------------- #
# Property-based tests.                                                       #
#                                                                              #
# This extractor only runs when the preferred markdown source is unavailable  #
# — it exists precisely because upstream HTML can't be assumed well-formed,   #
# so these assert it never raises regardless of how broken the markup is.     #
# --------------------------------------------------------------------------- #

_html_ish_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs", "Po"),
        whitelist_characters="<>/=\"'&;!-\n中",
    ),
    max_size=2000,
)


class TestHtmlProperties:
    @given(_html_ish_text)
    @settings(max_examples=200)
    def test_extract_text_never_raises(self, text: str) -> None:
        html.extract_text(text)

    @given(_html_ish_text)
    @settings(max_examples=200)
    def test_extract_code_blocks_never_raises(self, text: str) -> None:
        html.extract_code_blocks(text)

    @given(st.text(max_size=500))
    @settings(max_examples=200)
    def test_decode_html_entities_bounds_growth(self, text: str) -> None:
        out = html.decode_html_entities(text)
        # Entities only ever shrink or hold text length (multi-char entity ->
        # single char), never grow it.
        assert len(out) <= len(text)
