"""The shared FastMCP instance and tool annotations.

Split out from ``server.py`` so that both ``tools.py`` (which registers
tools via ``@mcp.tool``) and ``server.py`` (which owns process wiring:
logging, ``run()``) can import ``mcp`` without either module depending on
the other. Previously ``tools`` imported ``mcp``/``READONLY`` from
``server``, which itself had to import ``tools`` (for its registration
side effects) at the bottom of the file behind a ``# noqa: E402`` to dodge
the resulting cycle. Giving the shared instance its own module removes the
cycle at the root instead of reordering around it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp.server import FastMCP
from mcp_types import ToolAnnotations

from . import http

# Shared annotations: every tool is read-only and talks to the open web.
READONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await http.aclose()


# mask_error_details: only ToolError messages (the ones we deliberately author,
# e.g. in content.py) reach the client; any unanticipated exception is masked to
# a generic message, consistent with the rest of the server's defense-in-depth
# posture (host allowlist, size caps, input sanitization).
mcp = FastMCP("FastAPI-Docs-Expert", lifespan=_lifespan, mask_error_details=True)
