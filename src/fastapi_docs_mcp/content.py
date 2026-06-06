"""Content acquisition seam: markdown-preferred, HTML fallback.

Tools call here, never the fetch layers directly. This is where the "never breaks
on upstream change" guarantee lives: if the GitHub markdown source is unavailable
(repo reorganized, include macro changed, page missing there), we transparently
fall back to extracting the live documentation site.
"""

from __future__ import annotations

from . import html as html_fallback
from . import http, markdown
from .config import BASE_URL, MAX_CONTENT_LENGTH


async def _fetch_live_html(path: str) -> str | None:
    """Fetch the rendered doc page, retrying without the trailing slash."""
    p = path.strip().strip("/")
    return await http.fetch(f"{BASE_URL}/{p}/") or await http.fetch(f"{BASE_URL}/{p}")


async def get_page_text(path: str, max_length: int | None = None) -> str | None:
    """Clean documentation text for a path. Markdown first, HTML fallback."""
    limit = max_length if max_length is not None else MAX_CONTENT_LENGTH

    md = await markdown.to_clean_markdown(path)
    if md:
        return markdown.truncate_content(md, limit)

    html = await _fetch_live_html(path)
    if html:
        return markdown.truncate_content(html_fallback.extract_text(html), limit)
    return None


async def get_page_code(path: str) -> list[str]:
    """Python code examples for a path. Markdown/docs_src first, HTML fallback."""
    md = await markdown.fetch_markdown(path)
    if md:
        resolved = await markdown.resolve_includes(md)
        blocks = markdown.extract_python_blocks(resolved)
        if blocks:
            return blocks

    html = await _fetch_live_html(path)
    if html:
        return html_fallback.extract_code_blocks(html)
    return []
