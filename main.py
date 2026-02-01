"""
FastAPI Documentation MCP Server.

An MCP server that provides real-time access to FastAPI documentation,
enabling users to search, browse, and learn FastAPI concepts efficiently.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import httpx
from fastmcp import FastMCP

if TYPE_CHECKING:
    from collections.abc import Sequence

# Constants
BASE_URL = "https://fastapi.tiangolo.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
REQUEST_TIMEOUT = 30.0
MAX_CONTENT_LENGTH = 15_000

# Initialize MCP server
mcp = FastMCP("FastAPI-Docs-Expert")


async def fetch_url(url: str) -> str | None:
    """
    Fetch content from a URL with proper error handling.

    Args:
        url: The URL to fetch.

    Returns:
        The response text if successful, None otherwise.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError:
            return None


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
    entity_map = {
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
    for entity, char in entity_map.items():
        html = html.replace(entity, char)

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
    query_lower = query.lower().strip()

    urls = await fetch_sitemap()
    if not urls:
        return f"Could not fetch documentation. Browse at: {BASE_URL}"

    # Search for paths containing the query
    matching_paths = [
        url.replace(BASE_URL, "").strip("/")
        for url in urls
        if query_lower in url.lower()
    ]

    # Try keyword aliases if no direct match
    if not matching_paths:
        keyword_aliases = {
            "auth": "security",
            "login": "security",
            "oauth": "security",
            "jwt": "security",
            "token": "security",
            "password": "security",
            "database": "sql-databases",
            "db": "sql-databases",
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
            "inject": "dependencies",
            "dependency injection": "dependencies",
        }

        mapped_term = keyword_aliases.get(query_lower, query_lower)
        matching_paths = [
            url.replace(BASE_URL, "").strip("/")
            for url in urls
            if mapped_term in url.lower()
        ]

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
        block = block.replace("&lt;", "<").replace("&gt;", ">")
        block = block.replace("&amp;", "&").replace("&quot;", '"')
        block = block.replace("&#39;", "'").replace("&nbsp;", " ")
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

    # Map common terms to documentation paths
    topic_paths = {
        "cors": "tutorial/cors",
        "dependencies": "tutorial/dependencies",
        "dependency": "tutorial/dependencies",
        "di": "tutorial/dependencies",
        "security": "tutorial/security",
        "auth": "tutorial/security",
        "oauth": "tutorial/security/oauth2-jwt",
        "jwt": "tutorial/security/oauth2-jwt",
        "token": "tutorial/security/oauth2-jwt",
        "websocket": "advanced/websockets",
        "websockets": "advanced/websockets",
        "ws": "advanced/websockets",
        "middleware": "tutorial/middleware",
        "background": "tutorial/background-tasks",
        "background-tasks": "tutorial/background-tasks",
        "tasks": "tutorial/background-tasks",
        "testing": "tutorial/testing",
        "test": "tutorial/testing",
        "database": "tutorial/sql-databases",
        "sql": "tutorial/sql-databases",
        "sqlalchemy": "tutorial/sql-databases",
        "error": "tutorial/handling-errors",
        "exception": "tutorial/handling-errors",
        "validation": "tutorial/body-fields",
        "pydantic": "tutorial/body",
        "body": "tutorial/body",
        "query": "tutorial/query-params",
        "path": "tutorial/path-params",
        "header": "tutorial/header-params",
        "cookie": "tutorial/cookie-params",
        "form": "tutorial/request-forms",
        "file": "tutorial/request-files",
        "upload": "tutorial/request-files",
        "response": "tutorial/response-model",
        "first": "tutorial/first-steps",
        "start": "tutorial/first-steps",
        "hello": "tutorial/first-steps",
    }

    # Find the path for this topic
    doc_path = topic_paths.get(topic_lower)

    if not doc_path:
        # Try to find it in the sitemap
        urls = await fetch_sitemap()
        for url in urls:
            if topic_lower in url.lower():
                doc_path = url.replace(BASE_URL, "").strip("/")
                break

    if not doc_path:
        return f"""No examples found for '{topic}'.

Try: cors, dependencies, jwt, websockets, middleware, testing, database"""

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
    if not isinstance(pages, list):
        raise TypeError(f"Expected 'pages' to be a list, got {type(pages).__name__}")

    lines = [
        f"## {title}\n",
        f"*{description}*\n",
        "---\n",
    ]

    for page in pages:
        url = f"{BASE_URL}/{page}/"
        html = await fetch_url(url)

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

    # Find all pages matching the topic
    matching = [
        url.replace(BASE_URL, "").strip("/")
        for url in urls
        if topic_lower in url.lower()
    ]

    if not matching:
        return f"""No documentation found for '{topic}'.

Use `list_fastapi_pages()` to see available topics."""

    lines = [f"## Best Practices: {topic.title()}\n"]
    lines.append(f"*Found {len(matching)} relevant page(s)*\n\n---\n")

    # Fetch top pages (limit to avoid huge responses)
    for path in matching[:3]:
        url = f"{BASE_URL}/{path}/"
        html = await fetch_url(url)
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


if __name__ == "__main__":
    mcp.run()
