import asyncio

import pytest
from fastmcp.exceptions import ToolError

from fastapi_docs_mcp.concurrency import gather_all


async def _val(x: int, delay: float = 0) -> int:
    await asyncio.sleep(delay)
    return x


async def test_results_keep_call_order() -> None:
    assert await gather_all(_val(1, 0.02), _val(2), _val(3, 0.01)) == (1, 2, 3)


async def test_failure_propagates_unwrapped() -> None:
    async def boom() -> int:
        raise ToolError("unreachable")

    with pytest.raises(ToolError, match="unreachable"):
        await gather_all(_val(1), boom())


async def test_failure_cancels_siblings() -> None:
    finished = False

    async def slow() -> int:
        nonlocal finished
        await asyncio.sleep(0.2)
        finished = True
        return 1

    async def boom() -> int:
        raise ToolError("x")

    with pytest.raises(ToolError):
        await gather_all(slow(), boom())
    await asyncio.sleep(0.3)
    assert not finished  # asyncio.gather would have let this complete
