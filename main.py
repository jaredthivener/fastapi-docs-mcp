"""
FastAPI Documentation MCP Server.

An MCP server that provides real-time access to FastAPI documentation,
enabling users to search, browse, and learn FastAPI concepts efficiently.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING

import httpx
from fastmcp import FastMCP

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://fastapi.tiangolo.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
REQUEST_TIMEOUT = 30.0
MAX_CONTENT_LENGTH = 15_000

# Simple async-compatible TTL cache (no external dependencies)
_cache: dict[str, tuple[float, str]] = {}
_CACHE_TTL: float = 300.0  # 5 minutes

# HTML entity mapping for decoding
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

# Keyword aliases for search — maps synonyms to URL search terms.
# These are vocabulary mappings, NOT hardcoded paths — they work as long
# as the search term appears somewhere in the sitemap URLs.
_KEYWORD_ALIASES: dict[str, str] = {
    "auth": "security",
    "login": "security",
    "oauth": "security",
    "jwt": "security",
    "token": "security",  # nosec B105 - dict key, not a hardcoded credential
    "password": "security",  # nosec B105 - dict key, not a hardcoded credential
    "db": "sql-databases",
    "database": "sql-databases",
    "sqlalchemy": "sql-databases",
    "postgres": "sql-databases",
    "mysql": "sql-databases",
    "websocket": "websockets",
    "ws": "websockets",
    "realtime": "websockets",
    "start": "first-steps",
    "begin": "first-steps",
    "hello": "first-steps",
    "getting started": "first-steps",
    "di": "dependencies",
    "dependency": "dependencies",
    "inject": "dependencies",
    "dependency injection": "dependencies",
    "background": "background-tasks",
    "tasks": "background-tasks",
    "test": "testing",
    "exception": "handling-errors",
    "pydantic": "body",
    "upload": "request-files",
}

# Initialize MCP server
mcp = FastMCP("FastAPI-Docs-Expert")


def _cache_get(key: str) -> str | None:
    """Return cached value if it exists and hasn't expired."""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, value = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return value


def _cache_set(key: str, value: str) -> None:
    """Store a value in the cache with the current timestamp."""
    _cache[key] = (time.monotonic(), value)


async def fetch_url(url: str) -> str | None:
    """
    Fetch content from a URL with proper error handling.

    Args:
        url: The URL to fetch.

    Returns:
        The response text if successful, None otherwise.
    """
    cached = _cache_get(url)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            _cache_set(url, response.text)
            return response.text
        except httpx.TimeoutException:
            logger.warning("Timeout fetching %s", url)
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %d fetching %s", exc.response.status_code, url)
            return None
        except httpx.HTTPError as exc:
            logger.warning("HTTP error fetching %s: %s", url, exc)
            return None


def decode_html_entities(text: str) -> str:
    """
    Decode common HTML entities in text.

    Args:
        text: Text potentially containing HTML entities.

    Returns:
        Text with HTML entities decoded.
    """
    for entity, char in _HTML_ENTITIES.items():
        text = text.replace(entity, char)
    return text


def extract_text_from_html(html: str) -> str:
    """
    Extract readable text content from HTML.

    This uses regex-based extraction rather than a full HTML parser
    to keep dependencies minimal. The approach:
    1. Remove non-content elements (scripts, styles, navigation)
    2. Extract the main article content
    3. Strip remaining HTML tags
    4. Clean up whitespace

    Args:
        html: Raw HTML content.

    Returns:
        Clean text extracted from the HTML.
    """
    # Remove non-content elements
    html = re.sub(
        r"<(script|style|nav|footer|header)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Extract main article content if available
    article_match = re.search(
        r"<article[^>]*>(.*?)</article>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if article_match:
        html = article_match.group(1)

    # Iteratively remove HTML tags until stable
    previous = None
    while previous != html:
        previous = html
        html = re.sub(r"<[a-zA-Z/][^>]*>", "", html)

    # Decode common HTML entities AFTER removing tags
    html = decode_html_entities(html)

    # Clean up artifacts from malformed HTML
    html = re.sub(r"\s*>\s*", " ", html)
    html = re.sub(r'[a-zA-Z-]+=("[^"]*"|\'[^\']*\')\s*', "", html)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", html)
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


async def fetch_sitemap() -> list[str]:
    """
    Fetch all documentation URLs from the FastAPI sitemap.

    Returns:
        List of documentation URLs, or empty list if fetch fails.
    """
    content = await fetch_url(SITEMAP_URL)
    if not content:
        return []

    return re.findall(r"<loc>([^<]+)</loc>", content)


async def _search_sitemap_urls(query: str) -> list[str]:
    """
    Search sitemap URLs for a query, using keyword aliases as fallback.

    Args:
        query: The search term.

    Returns:
        List of matching documentation paths (without BASE_URL prefix).
    """
    query_lower = query.lower().strip()
    urls = await fetch_sitemap()
    if not urls:
        return []

    # Direct search
    matching = [
        url.replace(BASE_URL, "").strip("/")
        for url in urls
        if query_lower in url.lower()
    ]
    if matching:
        return matching

    # Try keyword alias
    mapped = _KEYWORD_ALIASES.get(query_lower, query_lower)
    if mapped != query_lower:
        matching = [
            url.replace(BASE_URL, "").strip("/")
            for url in urls
            if mapped in url.lower()
        ]
    return matching


def categorize_urls(urls: Sequence[str]) -> dict[str, list[str]]:
    """
    Categorize documentation URLs by section.

    Args:
        urls: List of full URLs from the sitemap.

    Returns:
        Dictionary mapping category names to lists of paths.
    """
    categories: dict[str, list[str]] = {
        "tutorial": [],
        "advanced": [],
        "deployment": [],
        "how-to": [],
        "reference": [],
        "other": [],
    }

    for url in urls:
        path = url.replace(BASE_URL, "").strip("/")
        if not path:
            continue

        categorized = False
        for category in categories:
            if category != "other" and (f"{category}/" in path or path == category):
                categories[category].append(path)
                categorized = True
                break

        if not categorized:
            categories["other"].append(path)

    return categories


def truncate_content(content: str, max_length: int = MAX_CONTENT_LENGTH) -> str:
    """
    Truncate content to a maximum length with a clean break.

    Args:
        content: The content to truncate.
        max_length: Maximum character length.

    Returns:
        Truncated content with indicator if truncated.
    """
    if len(content) <= max_length:
        return content

    # Try to break at a paragraph
    truncated = content[:max_length]
    last_break = truncated.rfind("\n\n")
    if last_break > max_length * 0.8:
        truncated = truncated[:last_break]

    return f"{truncated}\n\n... [Content truncated. Visit the URL for full content.]"


@mcp.tool
async def get_fastapi_docs(path: str) -> str:
    """
    Fetch FastAPI documentation content for any page.

    Args:
        path: The documentation path (e.g., "tutorial/first-steps",
              "tutorial/dependencies", "advanced/websockets").

    Returns:
        The documentation content from the official FastAPI website.
    """
    path = path.strip().strip("/")
    url = f"{BASE_URL}/{path}/"

    html = await fetch_url(url)

    # Retry without trailing slash if needed
    if not html:
        url = f"{BASE_URL}/{path}"
        html = await fetch_url(url)

    if html:
        content = extract_text_from_html(html)
        content = truncate_content(content)

        return f"""## FastAPI Documentation: {path}

**URL**: {url}

---

{content}"""

    return f"""Could not find documentation at '{url}'.

📖 **Browse the docs**: {BASE_URL}

Use `list_fastapi_pages()` to see all valid paths."""


@mcp.tool
async def search_fastapi_docs(query: str) -> str:
    """
    Search FastAPI documentation by keyword.

    Searches the sitemap for pages matching your query, with support
    for common aliases (e.g., "auth" finds security pages).

    Args:
        query: Search term (e.g., "authentication", "database",
               "websocket", "cors", "middleware").

    Returns:
        Documentation content for the best matching page.
    """
    matching_paths = await _search_sitemap_urls(query)

    if not matching_paths:
        return f"""No results for '{query}'.

📖 Browse: {BASE_URL}

Use `list_fastapi_pages()` to see all available pages."""

    # Fetch the best match
    best_match = matching_paths[0]
    url = f"{BASE_URL}/{best_match}/"
    html = await fetch_url(url)

    if not html:
        return f"Found '{best_match}' but could not fetch content."

    content = extract_text_from_html(html)
    content = truncate_content(content)

    # Include related pages if multiple matches
    related = ""
    if len(matching_paths) > 1:
        other_paths = matching_paths[1:5]
        related = "\n\n**Related pages:** " + ", ".join(f"`{p}`" for p in other_paths)

    return f"""## FastAPI Documentation: {best_match}

**URL**: {url}

---

{content}{related}"""


@mcp.tool
async def list_fastapi_pages() -> str:
    """
    List all available FastAPI documentation pages.

    Fetches the sitemap and returns a categorized list of all
    documentation pages available on fastapi.tiangolo.com.

    Returns:
        Categorized list of documentation paths.
    """
    urls = await fetch_sitemap()

    if not urls:
        return f"Could not fetch sitemap. Browse docs at: {BASE_URL}"

    categories = categorize_urls(urls)

    sections = [
        ("📚 Tutorial", "tutorial", 30),
        ("🔧 Advanced", "advanced", None),
        ("🚀 Deployment", "deployment", None),
        ("📖 How-To Guides", "how-to", None),
        ("📋 Reference", "reference", None),
    ]

    lines = ["## FastAPI Documentation Pages\n"]

    for header, key, limit in sections:
        paths = sorted(categories.get(key, []))
        if not paths:
            continue

        lines.append(f"### {header}")

        display_paths = paths[:limit] if limit else paths
        for path in display_paths:
            lines.append(f"- `{path}`")

        if limit and len(paths) > limit:
            lines.append(f"- ... and {len(paths) - limit} more")

        lines.append("")

    lines.append(f"**Total pages**: {len(urls)}")
    lines.append("")
    lines.append('💡 Use `get_fastapi_docs("path")` to fetch any page.')

    return "\n".join(lines)


def extract_code_blocks(html: str) -> list[str]:
    """
    Extract code blocks from HTML content.

    Args:
        html: Raw HTML content.

    Returns:
        List of code snippets found in the HTML.
    """
    code_blocks: list[str] = []

    # Match <pre><code> blocks (common pattern in docs)
    pre_code_pattern = r"<pre[^>]*><code[^>]*>(.*?)</code></pre>"
    matches = re.findall(pre_code_pattern, html, flags=re.DOTALL | re.IGNORECASE)
    code_blocks.extend(matches)

    # Match standalone <code> blocks with multiple lines
    code_pattern = r"<code[^>]*>(.*?)</code>"
    for match in re.findall(code_pattern, html, flags=re.DOTALL | re.IGNORECASE):
        if "\n" in match and len(match) > 50:
            code_blocks.append(match)

    # Clean up the code blocks
    cleaned: list[str] = []
    for block in code_blocks:
        # Remove any HTML tags FIRST (before entity decoding)
        block = re.sub(r"<[a-zA-Z/][^>]*>", "", block)
        # Then decode HTML entities
        block = decode_html_entities(block)
        block = block.strip()
        if block and len(block) > 20:
            cleaned.append(block)

    return cleaned


@mcp.tool
async def get_fastapi_example(topic: str) -> str:
    """
    Get code examples for a FastAPI topic. Returns just the code, no prose.

    Perfect for quick copy-paste when you know what you need.

    Args:
        topic: The topic to get examples for (e.g., "cors", "dependencies",
               "jwt", "websockets", "middleware", "background-tasks").

    Returns:
        Code examples extracted from the documentation.
    """
    topic_lower = topic.lower().strip()

    # Search sitemap dynamically (no hardcoded paths)
    matching_paths = await _search_sitemap_urls(topic_lower)

    if not matching_paths:
        return f"""No examples found for '{topic}'.

Try: cors, dependencies, jwt, websockets, middleware, testing, database"""

    doc_path = matching_paths[0]
    url = f"{BASE_URL}/{doc_path}/"
    html = await fetch_url(url)

    if not html:
        return f"Could not fetch examples from {url}"

    code_blocks = extract_code_blocks(html)

    if not code_blocks:
        return f"No code examples found in {doc_path}"

    # Format the output
    lines = [f"## Code Examples: {topic}\n", f"**Source**: {url}\n", "---\n"]

    for i, code in enumerate(code_blocks[:5], 1):  # Limit to 5 examples
        lines.append(f"### Example {i}\n")
        lines.append("```python")
        lines.append(code)
        lines.append("```\n")

    if len(code_blocks) > 5:
        lines.append(f"*... and {len(code_blocks) - 5} more examples in the docs.*")

    return "\n".join(lines)


@mcp.tool
async def compare_fastapi_approaches(topic: str) -> str:
    """
    Compare different approaches for a FastAPI topic.

    Shows side-by-side comparisons like sync vs async, different auth methods,
    or alternative patterns for the same functionality.

    Args:
        topic: What to compare (e.g., "sync-async", "auth-methods",
               "dependency-patterns", "response-types").

    Returns:
        Comparison of different approaches with code examples.
    """
    topic_lower = topic.lower().strip().replace(" ", "-")

    # Define comparison topics with their source pages
    comparisons: dict[str, dict[str, str | list[str]]] = {
        "sync-async": {
            "title": "Sync vs Async Functions",
            "pages": ["async", "tutorial/first-steps"],
            "description": "When to use async def vs def in FastAPI",
        },
        "async": {
            "title": "Sync vs Async Functions",
            "pages": ["async", "tutorial/first-steps"],
            "description": "When to use async def vs def in FastAPI",
        },
        "auth-methods": {
            "title": "Authentication Methods",
            "pages": [
                "tutorial/security/oauth2-jwt",
                "advanced/security/http-basic-auth",
                "tutorial/security",
            ],
            "description": "Different ways to handle authentication",
        },
        "auth": {
            "title": "Authentication Methods",
            "pages": [
                "tutorial/security/oauth2-jwt",
                "advanced/security/http-basic-auth",
                "tutorial/security",
            ],
            "description": "Different ways to handle authentication",
        },
        "security": {
            "title": "Authentication Methods",
            "pages": [
                "tutorial/security/oauth2-jwt",
                "advanced/security/http-basic-auth",
                "tutorial/security",
            ],
            "description": "Different ways to handle authentication",
        },
        "dependency-patterns": {
            "title": "Dependency Injection Patterns",
            "pages": [
                "tutorial/dependencies",
                "tutorial/dependencies/classes-as-dependencies",
                "tutorial/dependencies/dependencies-with-yield",
            ],
            "description": "Different ways to use dependency injection",
        },
        "dependencies": {
            "title": "Dependency Injection Patterns",
            "pages": [
                "tutorial/dependencies",
                "tutorial/dependencies/classes-as-dependencies",
                "tutorial/dependencies/dependencies-with-yield",
            ],
            "description": "Different ways to use dependency injection",
        },
        "response-types": {
            "title": "Response Types",
            "pages": [
                "tutorial/response-model",
                "advanced/response-directly",
                "advanced/custom-response",
            ],
            "description": "Different ways to return responses",
        },
        "response": {
            "title": "Response Types",
            "pages": [
                "tutorial/response-model",
                "advanced/response-directly",
                "advanced/custom-response",
            ],
            "description": "Different ways to return responses",
        },
        "testing": {
            "title": "Testing Approaches",
            "pages": ["tutorial/testing", "advanced/async-tests"],
            "description": "Sync vs async testing patterns",
        },
        "database": {
            "title": "Database Patterns",
            "pages": ["tutorial/sql-databases", "advanced/async-sql-databases"],
            "description": "Sync vs async database access",
        },
    }

    comparison = comparisons.get(topic_lower)

    if not comparison:
        return f"""No comparison found for '{topic}'.

**Available comparisons:**
- `sync-async` - When to use async def vs def
- `auth-methods` - OAuth2/JWT vs Basic Auth vs API Keys
- `dependency-patterns` - Functions, classes, and yield dependencies
- `response-types` - Response models vs direct responses
- `testing` - Sync vs async testing
- `database` - Sync vs async database access"""

    title = str(comparison["title"])
    description = str(comparison["description"])
    pages = comparison["pages"]
    if not isinstance(pages, list):  # pragma: no cover
        raise TypeError(f"Expected 'pages' to be a list, got {type(pages).__name__}")

    lines = [
        f"## {title}\n",
        f"*{description}*\n",
        "---\n",
    ]

    # Fetch all pages in parallel
    page_urls = [f"{BASE_URL}/{page}/" for page in pages]
    results = await asyncio.gather(*(fetch_url(url) for url in page_urls))

    for page, url, html in zip(pages, page_urls, results, strict=True):
        if not html:
            continue

        # Get page title from the content
        title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE)
        page_title = (
            extract_text_from_html(title_match.group(1)) if title_match else page
        )

        lines.append(f"### {page_title}\n")
        lines.append(f"**Docs**: {url}\n")

        # Get code examples
        code_blocks = extract_code_blocks(html)
        if code_blocks:
            lines.append("```python")
            lines.append(code_blocks[0])  # First example
            lines.append("```\n")

        # Get a brief description
        text = extract_text_from_html(html)
        # Take first ~300 chars as summary
        summary = text[:300].rsplit(" ", 1)[0] + "..."
        lines.append(f"> {summary}\n")

    return "\n".join(lines)


@mcp.tool
async def get_fastapi_best_practices(topic: str) -> str:
    """
    Get FastAPI best practices for a topic by fetching all relevant documentation.

    Searches the sitemap dynamically and returns combined content from
    multiple matching pages.

    Args:
        topic: The topic to get best practices for (e.g., "security",
               "testing", "database", "dependencies", "middleware").

    Returns:
        Combined content from all relevant documentation pages.
    """
    topic_lower = topic.lower().strip()

    urls = await fetch_sitemap()
    if not urls:
        return f"Could not fetch documentation. Browse at: {BASE_URL}"

    # Find all pages matching the topic, prioritized by section
    categories = categorize_urls(urls)
    priority_order = ["tutorial", "advanced", "how-to", "reference", "other"]
    matching = [
        path
        for cat in priority_order
        for path in categories.get(cat, [])
        if topic_lower in path.lower()
    ]

    if not matching:
        return f"""No documentation found for '{topic}'.

Use `list_fastapi_pages()` to see available topics."""

    lines = [f"## Best Practices: {topic.title()}\n"]
    lines.append(f"*Found {len(matching)} relevant page(s)*\n\n---\n")

    # Fetch top pages in parallel (limit to avoid huge responses)
    selected_paths = matching[:3]
    page_urls = [f"{BASE_URL}/{path}/" for path in selected_paths]
    results = await asyncio.gather(*(fetch_url(url) for url in page_urls))

    for path, url, html in zip(selected_paths, page_urls, results, strict=True):
        if not html:
            continue

        title_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE)
        title = extract_text_from_html(title_match.group(1)) if title_match else path

        content = extract_text_from_html(html)
        content = truncate_content(content, max_length=4000)

        lines.append(f"### {title}")
        lines.append(f"**URL**: {url}\n")
        lines.append(content)
        lines.append("\n---\n")

    if len(matching) > 3:
        more = ", ".join(f"`{p}`" for p in matching[3:8])
        lines.append(f"**More pages:** {more}")

    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    mcp.run()
