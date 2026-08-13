"""Tests for the lean HTML→text/code fallback extractor."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from fastapi_docs_mcp import html


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
