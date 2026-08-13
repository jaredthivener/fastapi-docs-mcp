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


class UpstreamError(Exception):
    """Raised when a fetch could not be completed (timeout, network error, non-404
    HTTP status). Distinct from a confirmed-absent resource, which is ``None`` —
    callers must not treat the two as equivalent (see ``content.py``)."""


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
    """Stream a response, enforcing the allowlist (post-redirect) and size cap.

    Returns ``None`` only for a *confirmed absence* (HTTP 404) or a
    security-relevant refusal (disallowed host/redirect) — both fail closed and
    quiet by design. Anything else that prevents a real answer (timeout,
    connection error, non-404 HTTP status) raises ``UpstreamError``, since the
    caller cannot tell "doesn't exist" from "couldn't check" from ``None`` alone.
    """
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
    except httpx.TimeoutException as exc:
        logger.warning("Timeout fetching %s", url)
        raise UpstreamError(f"Timeout fetching {url}") from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.warning("HTTP %d fetching %s", status, url)
        if status == 404:
            return None
        raise UpstreamError(f"HTTP {status} fetching {url}") from exc
    except httpx.HTTPError as exc:
        logger.warning("HTTP error fetching %s: %s", url, exc)
        raise UpstreamError(f"HTTP error fetching {url}: {exc}") from exc


async def fetch(url: str) -> str | None:
    """Fetch ``url`` (cached, single-flight).

    Returns text, or ``None`` for a confirmed-absent/disallowed resource.
    Raises ``UpstreamError`` if the fetch could not be completed at all.
    """
    return await cache.get_or_fetch(url, lambda: _download(url))
