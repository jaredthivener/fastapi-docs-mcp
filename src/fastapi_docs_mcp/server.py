"""MCP server wiring: logging, the FastMCP instance, tool registration, run()."""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolAnnotations

from . import http

# stdio is the MCP transport on stdout, so logs MUST go to stderr.
logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Shared annotations: every tool is read-only and talks to the open web.
READONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


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

# Importing tools registers the @mcp.tool functions on the instance above.
# (Imported last to avoid a circular import: tools depends on `mcp`/`READONLY`.)
from . import tools as tools  # noqa: E402,F401


def run() -> None:  # pragma: no cover
    mcp.run(transport="stdio")
