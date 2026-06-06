"""The six MCP tools — thin orchestration over discovery + content layers."""

from __future__ import annotations

import re
from typing import TypedDict

from . import content, sitemap
from .config import BASE_URL, MAX_INPUT_LENGTH
from .server import READONLY, mcp


class _Comparison(TypedDict):
    title: str
    pages: list[str]
    description: str


# Curated comparisons: canonical configs + an alias map (no duplicated bodies).
# Pages are validated against the live sitemap at runtime, so stale entries are
# dropped rather than emitted as dead sections.
_COMPARISONS: dict[str, _Comparison] = {
    "sync-async": {
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
    "dependency-patterns": {
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
_COMPARE_ALIASES: dict[str, str] = {
    "async": "sync-async",
    "auth": "auth-methods",
    "security": "auth-methods",
    "dependencies": "dependency-patterns",
    "response": "response-types",
}

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _clean_arg(value: str) -> str:
    """Length-cap and strip control characters from a tool argument."""
    return _CONTROL_RE.sub("", value.strip())[:MAX_INPUT_LENGTH]


def _clean_path(path: str) -> str:
    """Sanitize a doc path: no control chars, no traversal, no leading slashes."""
    cleaned = _clean_arg(path).strip("/")
    return "/".join(seg for seg in cleaned.split("/") if seg not in ("", ".", ".."))


def _first_heading(md: str, default: str) -> str:
    m = _HEADING_RE.search(md)
    return m.group(1).strip() if m else default


def _summary(md: str, limit: int = 220) -> str:
    """First prose paragraph, code/headings removed, capped to ~limit chars."""
    text = re.sub(r"```.*?```", "", md, flags=re.DOTALL)
    text = _HEADING_RE.sub("", text).strip()
    snippet = text[:limit]
    if len(text) > limit:
        snippet = snippet.rsplit(" ", 1)[0] + "..."
    return snippet


def _cap_code(code: str, max_lines: int = 18) -> str:
    """Trim a code block to a representative head (compare view is illustrative)."""
    lines = code.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["# ..."]
    return "\n".join(lines)


@mcp.tool(annotations=READONLY)
async def get_fastapi_docs(path: str) -> str:
    """Fetch FastAPI documentation content for a page by its path.

    Args:
        path: Doc path, e.g. "tutorial/first-steps" or "advanced/websockets".
    """
    path = _clean_path(path)
    url = f"{BASE_URL}/{path}/"
    text = await content.get_page_text(path)

    if text:
        return f"## FastAPI Documentation: {path}\n\n**URL**: {url}\n\n---\n\n{text}"

    return f"""Could not find documentation at '{url}'.

📖 **Browse the docs**: {BASE_URL}

Use `list_fastapi_pages()` to see all valid paths."""


@mcp.tool(annotations=READONLY)
async def search_fastapi_docs(query: str) -> str:
    """Search the docs by keyword and return the best-matching page.

    Common aliases are supported (e.g. "auth" finds security pages).

    Args:
        query: Search term, e.g. "cors", "database", or "websocket".
    """
    query = _clean_arg(query)
    matching_paths = await sitemap.search_sitemap_urls(query)

    if not matching_paths:
        return f"""No results for '{query}'.

📖 Browse: {BASE_URL}

Use `list_fastapi_pages()` to see all available pages."""

    best_match = matching_paths[0]
    url = f"{BASE_URL}/{best_match}/"
    text = await content.get_page_text(best_match)

    if not text:
        return f"Found '{best_match}' but could not fetch content."

    related = ""
    if len(matching_paths) > 1:
        other_paths = matching_paths[1:5]
        related = "\n\n**Related pages:** " + ", ".join(f"`{p}`" for p in other_paths)

    return (
        f"## FastAPI Documentation: {best_match}\n\n"
        f"**URL**: {url}\n\n---\n\n{text}{related}"
    )


@mcp.tool(annotations=READONLY)
async def list_fastapi_pages() -> str:
    """List all available FastAPI doc pages, categorized by section."""
    urls = await sitemap.fetch_sitemap()
    if not urls:
        return f"Could not fetch sitemap. Browse docs at: {BASE_URL}"

    categories = sitemap.categorize_urls(urls)
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
        lines.extend(f"- `{path}`" for path in display_paths)
        if limit and len(paths) > limit:
            lines.append(f"- ... and {len(paths) - limit} more")
        lines.append("")

    lines.append(f"**Total pages**: {len(urls)}")
    lines.append("")
    lines.append('💡 Use `get_fastapi_docs("path")` to fetch any page.')
    return "\n".join(lines)


@mcp.tool(annotations=READONLY)
async def get_fastapi_example(topic: str) -> str:
    """Get code examples (no prose) for a FastAPI topic.

    Args:
        topic: Topic to fetch examples for, e.g. "cors", "jwt", or "websockets".
    """
    topic_clean = _clean_arg(topic).lower()
    matching_paths = await sitemap.search_sitemap_urls(topic_clean)

    if not matching_paths:
        return f"""No examples found for '{topic}'.

Try: cors, dependencies, jwt, websockets, middleware, testing, database"""

    doc_path = matching_paths[0]
    url = f"{BASE_URL}/{doc_path}/"
    code_blocks = await content.get_page_code(doc_path)

    if not code_blocks:
        return f"No code examples found in {doc_path}"

    lines = [f"## Code Examples: {topic}\n", f"**Source**: {url}\n", "---\n"]
    for i, code in enumerate(code_blocks[:5], 1):
        lines.append(f"### Example {i}\n")
        lines.append("```python")
        lines.append(code)
        lines.append("```\n")

    if len(code_blocks) > 5:
        lines.append(f"*... and {len(code_blocks) - 5} more examples in the docs.*")
    return "\n".join(lines)


@mcp.tool(annotations=READONLY)
async def compare_fastapi_approaches(topic: str) -> str:
    """Compare FastAPI approaches side-by-side (e.g. sync vs async, auth methods).

    Args:
        topic: What to compare, e.g. "sync-async", "auth-methods", or any topic.
    """
    topic_clean = _clean_arg(topic).lower().replace(" ", "-")
    key = _COMPARE_ALIASES.get(topic_clean, topic_clean)
    comparison = _COMPARISONS.get(key)

    sitemap_urls = await sitemap.fetch_sitemap()
    valid_paths = {u.replace(BASE_URL, "").strip("/") for u in sitemap_urls}

    if comparison:
        title = comparison["title"]
        description = comparison["description"]
        configured = comparison["pages"]
        # Self-heal: keep only pages the sitemap still knows about.
        pages = [p for p in configured if p in valid_paths] or configured
    else:
        # Dynamic fallback: compare the top sibling pages matching the topic.
        found = await sitemap.search_sitemap_urls(topic_clean)
        if not found:
            return _compare_help(topic)
        title = f"{topic.strip().title()} Approaches"
        description = f"Pages matching '{topic.strip()}'"
        pages = found[:3]

    lines = [f"## {title}\n", f"*{description}*\n", "---\n"]
    for page in pages:
        text = await content.get_page_text(page, max_length=3200)
        if not text:
            continue
        code_blocks = await content.get_page_code(page)
        lines.append(f"### {_first_heading(text, page)}\n")
        lines.append(f"**Docs**: {BASE_URL}/{page}/\n")
        if code_blocks:
            lines.append("```python")
            lines.append(_cap_code(code_blocks[0]))
            lines.append("```\n")
        lines.append(f"> {_summary(text)}\n")

    return "\n".join(lines)


def _compare_help(topic: str) -> str:
    return f"""No comparison found for '{topic}'.

**Available comparisons:**
- `sync-async` - When to use async def vs def
- `auth-methods` - OAuth2/JWT vs Basic Auth vs API Keys
- `dependency-patterns` - Functions, classes, and yield dependencies
- `response-types` - Response models vs direct responses
- `testing` - Sync vs async testing
- `database` - Sync vs async database access

Or pass any topic to compare matching pages dynamically."""


@mcp.tool(annotations=READONLY)
async def get_fastapi_best_practices(topic: str) -> str:
    """Combine best-practice content from all doc pages matching a topic.

    Args:
        topic: Topic to gather, e.g. "security", "testing", or "dependencies".
    """
    topic_clean = _clean_arg(topic).lower()
    urls = await sitemap.fetch_sitemap()
    if not urls:
        return f"Could not fetch documentation. Browse at: {BASE_URL}"

    categories = sitemap.categorize_urls(urls)
    priority_order = ["tutorial", "advanced", "how-to", "reference", "other"]
    matching = [
        path
        for cat in priority_order
        for path in categories.get(cat, [])
        if topic_clean in path.lower()
    ]

    if not matching:
        return f"""No documentation found for '{topic}'.

Use `list_fastapi_pages()` to see available topics."""

    lines = [
        f"## Best Practices: {topic.strip().title()}\n",
        f"*Found {len(matching)} relevant page(s)*\n\n---\n",
    ]
    for path in matching[:3]:
        text = await content.get_page_text(path, max_length=3200)
        if not text:
            continue
        lines.append(f"### {_first_heading(text, path)}")
        lines.append(f"**URL**: {BASE_URL}/{path}/\n")
        lines.append(text)
        lines.append("\n---\n")

    if len(matching) > 3:
        more = ", ".join(f"`{p}`" for p in matching[3:8])
        lines.append(f"**More pages:** {more}")
    return "\n".join(lines)
