"""Content acquisition seam: markdown-preferred, HTML fallback.

Tools call here, never the fetch layers directly. This is where the "never breaks
on upstream change" guarantee lives: if the GitHub markdown source is unavailable
(repo reorganized, include macro changed, page missing there), we transparently
fall back to extracting the live documentation site.

This is also the one place that turns a *confirmed* absence (the page genuinely
doesn't exist — returns ``None``, handled softly by ``tools.py``) into a distinct
outcome from an *unconfirmed* one (every source failed transiently — raises
``ToolError``, per MCP's ``isError`` tool-execution-error channel). Collapsing
those two into the same "not found" text would misinform the caller and silently
defeat the fallback seam's resilience guarantee under a shared outage.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

from . import html as html_fallback
from . import http, markdown
from .config import BASE_URL, MAX_CONTENT_LENGTH

_UNREACHABLE_MSG = (
    "Could not reach fastapi.tiangolo.com or GitHub to fetch '{path}' — this "
    "doesn't mean the page doesn't exist. Try again shortly."
)


async def _fetch_live_html(path: str) -> str | None:
    """Fetch the rendered doc page, retrying without the trailing slash.

    Raises ``http.UpstreamError`` only if *both* URL forms fail transiently.
    """
    p = path.strip().strip("/")
    had_error = False
    for url in (f"{BASE_URL}/{p}/", f"{BASE_URL}/{p}"):
        try:
            html = await http.fetch(url)
        except http.UpstreamError:
            had_error = True
            continue
        if html:
            return html
    if had_error:
        raise http.UpstreamError(f"Could not fetch live page for path: {path}")
    return None


async def get_page_text(path: str, max_length: int | None = None) -> str | None:
    """Clean documentation text for a path. Markdown first, HTML fallback.

    A confirmed absence on both sources (no content, no error) returns
    ``None`` — a legitimate empty result, not an error. ``ToolError`` is
    raised only when *neither* source could even confirm the page is
    missing (both failed transiently), since collapsing that into the same
    "not found" text would misinform the caller and defeat the fallback
    seam's own resilience guarantee.
    """
    limit = max_length if max_length is not None else MAX_CONTENT_LENGTH

    md, md_failed = None, False
    try:
        md = await markdown.to_clean_markdown(path)
    except http.UpstreamError:
        md_failed = True
    if md:
        return markdown.truncate_content(md, limit)

    html, html_failed = None, False
    try:
        html = await _fetch_live_html(path)
    except http.UpstreamError:
        html_failed = True
    if html:
        return markdown.truncate_content(html_fallback.extract_text(html), limit)

    if md_failed and html_failed:
        raise ToolError(_UNREACHABLE_MSG.format(path=path))
    return None


async def get_page_code(path: str) -> list[str]:
    """Python code examples for a path. Markdown/docs_src first, HTML fallback.

    Same confirmed-absent-vs-unreachable distinction as ``get_page_text``.
    """
    md, md_failed = None, False
    try:
        md = await markdown.fetch_markdown(path)
    except http.UpstreamError:
        md_failed = True
    if md:
        resolved = await markdown.resolve_includes(md)
        blocks = markdown.extract_python_blocks(resolved)
        if blocks:
            return blocks

    html, html_failed = None, False
    try:
        html = await _fetch_live_html(path)
    except http.UpstreamError:
        html_failed = True
    if html:
        return html_fallback.extract_code_blocks(html)

    if md_failed and html_failed:
        raise ToolError(_UNREACHABLE_MSG.format(path=path))
    return []
