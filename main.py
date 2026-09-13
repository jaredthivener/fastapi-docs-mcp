"""Entrypoint shim for the FastAPI Docs MCP server.

The implementation lives in the ``fastapi_docs_mcp`` package; this module keeps a
stable ``main.py`` entrypoint (referenced by the Dockerfile and .vscode/mcp.json)
and re-exports the tool callables for convenience.
"""

from __future__ import annotations

from fastapi_docs_mcp import (
    compare_fastapi_approaches,
    get_fastapi_best_practices,
    get_fastapi_docs,
    get_fastapi_example,
    list_fastapi_pages,
    mcp,
    run,
    search_fastapi_docs,
)

__all__ = [
    "compare_fastapi_approaches",
    "get_fastapi_best_practices",
    "get_fastapi_docs",
    "get_fastapi_example",
    "list_fastapi_pages",
    "mcp",
    "search_fastapi_docs",
]


if __name__ == "__main__":  # pragma: no cover
    run()
