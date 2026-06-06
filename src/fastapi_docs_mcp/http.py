"""The single network choke point.

Exposes one pooled, loop-aware ``httpx.AsyncClient`` and a ``fetch`` helper that
enforces the host allowlist, caps download size, and routes every request
through the single-flight cache.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlsplit

import httpx

from . import cache
from .config import (
    ALLOWED_HOSTS,
    MAX_DOWNLOAD_BYTES,
    REQUEST_TIMEOUT,
    USER_AGENT,
)

logger = logging.getLogger(__name__)

# A persistent client gives connection reuse / keep-alive. httpx clients are
# bound to the event loop they run on, so we key the singleton by loop: one
# client per loop (reused within it), which also keeps pytest's function-scoped
# loops from reusing a client tied to a closed loop.
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        follow_redirects=True,
        timeout=REQUEST_TIMEOUT,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        headers={"User-Agent": USER_AGENT},
    )


def get_client() -> httpx.AsyncClient:
    """Return the shared client for the running loop, creating it if needed."""
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _client_loop is not loop:
        _client = _new_client()
        _client_loop = loop
    return _client


async def aclose() -> None:
    """Close the shared client (called from the server lifespan on shutdown)."""
    global _client, _client_loop
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
    _client_loop = None


def _host_allowed(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host in ALLOWED_HOSTS


async def _download(url: str) -> str | None:
    """Stream a response, enforcing the allowlist (post-redirect) and size cap."""
    if not _host_allowed(url):
        logger.warning("Refusing fetch of disallowed host: %s", url)
        return None

    client = get_client()
    try:
        async with client.stream("GET", url) as response:
            # Reject redirects that landed off-allowlist.
            if not _host_allowed(str(response.url)):
                logger.warning("Redirect left allowlist: %s", response.url)
                return None
            response.raise_for_status()

            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    logger.warning("Response exceeded size cap: %s", url)
                    break
                chunks.append(chunk)

            encoding = response.encoding or "utf-8"
            return b"".join(chunks).decode(encoding, errors="replace")
    except httpx.TimeoutException:
        logger.warning("Timeout fetching %s", url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("HTTP %d fetching %s", exc.response.status_code, url)
        return None
    except httpx.HTTPError as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc)
        return None


async def fetch(url: str) -> str | None:
    """Fetch ``url`` (cached, single-flight). Returns text or ``None`` on failure."""
    return await cache.get_or_fetch(url, lambda: _download(url))
