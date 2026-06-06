"""Lean HTML→text/code extraction — the resilience fallback only.

Used when the markdown source is unavailable for a page. Slimmer than the
original regex pipeline (no iterate-until-stable loop), but good enough to keep
every sitemap-discoverable page reachable.
"""

from __future__ import annotations

import re

_HTML_ENTITIES: dict[str, str] = {
    "&lt;": "<",
    "&gt;": ">",
    "&amp;": "&",
    "&quot;": '"',
    "&#39;": "'",
    "&nbsp;": " ",
    "&para;": "",
    "&sect;": "",
    "&apos;": "'",
}

_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")
_NONCONTENT_RE = re.compile(
    r"<(script|style|nav|footer|header)[^>]*>.*?</\1>",
    flags=re.DOTALL | re.IGNORECASE,
)
_ARTICLE_RE = re.compile(
    r"<article[^>]*>(.*?)</article>", flags=re.DOTALL | re.IGNORECASE
)
_ATTR_RE = re.compile(r'[a-zA-Z-]+=("[^"]*"|\'[^\']*\')\s*')
_PRE_CODE_RE = re.compile(
    r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", flags=re.DOTALL | re.IGNORECASE
)
_CODE_RE = re.compile(r"<code[^>]*>(.*?)</code>", flags=re.DOTALL | re.IGNORECASE)


def decode_html_entities(text: str) -> str:
    """Decode the handful of HTML entities that appear in FastAPI docs."""
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return text


def extract_text(html: str) -> str:
    """Extract readable text from an HTML page."""
    html = _NONCONTENT_RE.sub("", html)

    article = _ARTICLE_RE.search(html)
    if article:
        html = article.group(1)

    html = _TAG_RE.sub("", html)
    html = decode_html_entities(html)

    # Clean artifacts left by malformed markup.
    html = re.sub(r"\s*>\s*", " ", html)
    html = _ATTR_RE.sub("", html)

    text = re.sub(r"[ \t]+", " ", html)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def extract_code_blocks(html: str) -> list[str]:
    """Extract code snippets from an HTML page."""
    blocks: list[str] = list(_PRE_CODE_RE.findall(html))
    for match in _CODE_RE.findall(html):
        if "\n" in match and len(match) > 50:
            blocks.append(match)

    cleaned: list[str] = []
    for block in blocks:
        block = _TAG_RE.sub("", block)
        block = decode_html_entities(block).strip()
        if len(block) > 20:
            cleaned.append(block)
    return cleaned
