"""MCP server wiring: logging, tool registration, run()."""

from __future__ import annotations

import logging
import sys

# Importing tools registers the @mcp.tool functions onto the `mcp` instance
# imported below; the `as tools` re-export idiom tells the linter this
# import is deliberate even though the name itself is never used further.
from . import tools as tools
from .app import mcp

# stdio is the MCP transport on stdout, so logs MUST go to stderr.
logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def run() -> None:  # pragma: no cover
    """Run the server over the stdio transport."""
    mcp.run(transport="stdio")
