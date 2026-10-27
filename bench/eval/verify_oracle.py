"""Harness self-test, no API cost: oracle must pass, null answers must fail.

Runs each case's oracle tool call(s) through an in-process FastMCP client and
asserts the grader accepts the concatenated output (gold is recoverable from the
server) and rejects empty / constant answers (grader not too lenient).
"""

from __future__ import annotations

import asyncio
import logging

from fastmcp import Client

from fastapi_docs_mcp import cache, http, mcp

from .cases import CASES
from .grade import grade


async def main() -> int:
    """Run the oracle and null checks; return a process exit code."""
    logging.disable(logging.CRITICAL)
    bad = 0
    async with Client(mcp) as client:
        for case in CASES:
            if not case.tools_expected:
                assert grade(case, "Sorry, out of scope.", 0)
                assert not grade(case, "Sorry, out of scope.", 1)
                print(f"ok    {case.id:22} (off-scope: passes only with 0 tool calls)")
                continue
            text = ""
            for name, args in case.oracle:
                cache.clear()
                res = await client.call_tool(name, args)
                text += "".join(b.text for b in res.content if hasattr(b, "text"))
            oracle_ok = grade(case, text, 1)
            null_ok = grade(case, "", 0) or grade(case, "I don't know.", 0)
            status = "ok   " if oracle_ok and not null_ok else "FAIL "
            bad += status == "FAIL "
            print(f"{status} {case.id:22} oracle={oracle_ok} null_passes={null_ok}")
    await http.aclose()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
