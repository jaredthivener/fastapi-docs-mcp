"""Central configuration: URLs, allowlist, limits, and cache tuning.

Every magic value the server depends on lives here so behavior can be reasoned
about (and adjusted) in one place.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Final

try:
    _VERSION = version("fastapi-docs-mcp")
except PackageNotFoundError:  # pragma: no cover - only when run unpackaged
    _VERSION = "0.0.0"

# --- Upstream sources -------------------------------------------------------
BASE_URL: Final = "https://fastapi.tiangolo.com"
SITEMAP_URL: Final = f"{BASE_URL}/sitemap.xml"

# Raw markdown lives under docs/en/docs; example code (docs_src) at the repo root.
REPO_RAW_ROOT: Final = "https://raw.githubusercontent.com/fastapi/fastapi/master"
DOCS_RAW_BASE: Final = f"{REPO_RAW_ROOT}/docs/en/docs"

# Hosts the server is permitted to fetch from (enforced after redirects).
ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    {"fastapi.tiangolo.com", "raw.githubusercontent.com"}
)

# --- Network ----------------------------------------------------------------
# Split rather than one blanket timeout: a dead/unreachable upstream would
# otherwise block for the full duration on connect alone, before content.py's
# fallback (markdown -> HTML, two URL forms) ever gets a chance to move on.
CONNECT_TIMEOUT: Final = 5.0
READ_TIMEOUT: Final = 15.0
WRITE_TIMEOUT: Final = 5.0
POOL_TIMEOUT: Final = 5.0

# Also used as an in-process asyncio.Semaphore bound in http.py. The tools
# layer can fan out well beyond this (e.g. compare_fastapi_approaches
# gathering 3 pages, each resolving up to MAX_INCLUDES docs_src fetches
# concurrently) -- bounding concurrent fetch *attempts* to what the pool can
# serve immediately means excess callers queue on our own semaphore (no
# timeout) instead of racing httpx's connection pool (a hard POOL_TIMEOUT).
MAX_CONCURRENT_FETCHES: Final = 20
MAX_DOWNLOAD_BYTES: Final = 5_000_000  # hard cap on any single response body
USER_AGENT: Final = (
    f"fastapi-docs-mcp/{_VERSION} (+https://github.com/jaredthivener/fastapi-docs-mcp)"
)

# --- Cache ------------------------------------------------------------------
# Docs are near-static; a long TTL slashes upstream calls. LRU-bounded so the
# cache can never grow without limit.
CACHE_TTL: Final = 6 * 60 * 60.0  # 6 hours
CACHE_MAX_ENTRIES: Final = 256

# --- Output / token budget --------------------------------------------------
MAX_CONTENT_LENGTH: Final = 15_000

# --- Input validation -------------------------------------------------------
MAX_INPUT_LENGTH: Final = 256

# --- Include resolution -----------------------------------------------------
MAX_INCLUDES: Final = 16  # cap docs_src fetches per page
