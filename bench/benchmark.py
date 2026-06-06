#!/usr/bin/env python
"""
Token benchmark for the FastAPI Docs MCP tools.

Runs each tool with a fixed, representative input and measures the size of the
returned payload in characters and tokens. Token counts use tiktoken's
``cl100k_base`` as a deterministic proxy for LLM tokenization — absolute numbers
are approximate, but the BEFORE/AFTER comparison (same encoder, same inputs) is
apples-to-apples.

Usage:
    uv run --with tiktoken python bench/benchmark.py [label]

Writes JSON to stdout. Redirect to capture, e.g.:
    uv run --with tiktoken python bench/benchmark.py before > bench/before.json
"""

from __future__ import annotations

import asyncio
import json
import sys

import main
from fastapi_docs_mcp import cache

# Fixed benchmark matrix: (tool_name, args). Mirrors the manual smoke tests so
# results are comparable to historical runs.
BENCH: list[tuple[str, tuple[str, ...]]] = [
    ("get_fastapi_docs", ("tutorial/first-steps",)),
    ("search_fastapi_docs", ("cors",)),
    ("list_fastapi_pages", ()),
    ("get_fastapi_example", ("cors",)),
    ("compare_fastapi_approaches", ("auth-methods",)),
    ("get_fastapi_best_practices", ("security",)),
]


def _resolve(name: str):  # type: ignore[no-untyped-def]
    """Return the awaitable underlying function for a tool name.

    FastMCP wraps tool functions in a Tool object exposing ``.fn``; fall back to
    the attribute itself if it is already a plain callable.
    """
    obj = getattr(main, name)
    return getattr(obj, "fn", obj)


def _count_tokens(text: str) -> int:
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


async def run() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "run"

    # Start from a cold cache so timings/sizes reflect a real first call.
    cache.clear()

    rows: dict[str, dict[str, int]] = {}
    for name, args in BENCH:
        fn = _resolve(name)
        out = await fn(*args)
        rows[name] = {"chars": len(out), "tokens": _count_tokens(out)}

    total_tokens = sum(r["tokens"] for r in rows.values())
    total_chars = sum(r["chars"] for r in rows.values())

    print(
        json.dumps(
            {
                "label": label,
                "tools": rows,
                "total": {"chars": total_chars, "tokens": total_tokens},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(run())
