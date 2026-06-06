"""Central configuration: URLs, allowlist, limits, and cache tuning.

Every magic value the server depends on lives here so behavior can be reasoned
about (and adjusted) in one place.
"""

from __future__ import annotations

from typing import Final

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
REQUEST_TIMEOUT: Final = 30.0
MAX_DOWNLOAD_BYTES: Final = 5_000_000  # hard cap on any single response body
USER_AGENT: Final = (
    "fastapi-docs-mcp/2.0 (+https://github.com/jaredthivener/fastapi-docs-mcp)"
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
