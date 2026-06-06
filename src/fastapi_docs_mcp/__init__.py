"""FastAPI Documentation MCP Server.

A FastMCP server providing real-time, token-efficient access to FastAPI
documentation. Public surface is re-exported here for convenience.
"""

from __future__ import annotations

from .server import mcp, run
from .tools import (
    compare_fastapi_approaches,
    get_fastapi_best_practices,
    get_fastapi_docs,
    get_fastapi_example,
    list_fastapi_pages,
    search_fastapi_docs,
)

__all__ = [
    "mcp",
    "run",
    "get_fastapi_docs",
    "search_fastapi_docs",
    "list_fastapi_pages",
    "get_fastapi_example",
    "compare_fastapi_approaches",
    "get_fastapi_best_practices",
]
