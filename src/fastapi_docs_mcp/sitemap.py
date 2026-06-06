"""Discovery layer — the sitemap is the single source of truth for page paths.

Nothing here hardcodes a page inventory; everything is derived from the live
sitemap so new/renamed upstream docs are found automatically.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from . import http
from .config import BASE_URL, SITEMAP_URL

# Keyword aliases map user vocabulary to terms that appear in sitemap URLs.
# These are synonyms, NOT hardcoded paths — they keep working as long as the
# mapped term shows up somewhere in the sitemap.
KEYWORD_ALIASES: dict[str, str] = {
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

_LOC_RE = re.compile(r"<loc>([^<]+)</loc>")


async def fetch_sitemap() -> list[str]:
    """Return all documentation URLs from the sitemap (empty list on failure)."""
    content = await http.fetch(SITEMAP_URL)
    if not content:
        return []
    return _LOC_RE.findall(content)


async def search_sitemap_urls(query: str) -> list[str]:
    """Return sitemap paths matching ``query``, falling back to keyword aliases."""
    query_lower = query.lower().strip()
    urls = await fetch_sitemap()
    if not urls:
        return []

    matching = [
        url.replace(BASE_URL, "").strip("/")
        for url in urls
        if query_lower in url.lower()
    ]
    if matching:
        return matching

    mapped = KEYWORD_ALIASES.get(query_lower, query_lower)
    if mapped != query_lower:
        matching = [
            url.replace(BASE_URL, "").strip("/")
            for url in urls
            if mapped in url.lower()
        ]
    return matching


def categorize_urls(urls: Sequence[str]) -> dict[str, list[str]]:
    """Bucket sitemap URLs into documentation sections."""
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

        for category in categories:
            if category != "other" and (f"{category}/" in path or path == category):
                categories[category].append(path)
                break
        else:
            categories["other"].append(path)

    return categories
