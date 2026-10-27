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
    "token": "security",
    "password": "security",
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


_STOPWORDS = frozenset(
    {"a", "an", "the", "to", "in", "of", "and", "for", "with", "how"}
)


def match_paths(query: str, paths: Sequence[str]) -> list[str]:
    """Rank ``paths`` for ``query``: exact slug, alias, then per-word match.

    A phrase is tried as a slug first ("background tasks" -> ``background-tasks``),
    then as an alias; otherwise each word (aliased) must prefix-match a path
    word, and paths matching more words rank first, shorter (more general)
    paths breaking ties.
    """
    query = query.lower().strip()
    slug = "-".join(re.findall(r"[a-z0-9]+", query))
    for needle in (query, slug, KEYWORD_ALIASES.get(query), KEYWORD_ALIASES.get(slug)):
        if needle and (hits := [p for p in paths if needle in p.lower()]):
            return hits
    words = re.findall(r"[a-z0-9]+", query)
    words = [w for w in words if w not in _STOPWORDS] or words
    if len(words) < 2:  # a lone word: retry it bare unless that was the query
        return match_paths(words[0], paths) if words and words[0] != query else []
    terms = [KEYWORD_ALIASES.get(w, w) for w in words]

    def score(path: str) -> int:
        path_words = re.findall(r"[a-z0-9]+", path.lower())
        return sum(any(w.startswith(t) for w in path_words) for t in terms)

    scored = [(score(p), p) for p in paths]
    return [p for s, p in sorted(scored, key=lambda x: (-x[0], len(x[1]))) if s]


async def search_sitemap_urls(query: str) -> list[str]:
    """Return sitemap paths matching ``query`` (see :func:`match_paths`)."""
    urls = await fetch_sitemap()
    return match_paths(query, [u.replace(BASE_URL, "").strip("/") for u in urls])


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
