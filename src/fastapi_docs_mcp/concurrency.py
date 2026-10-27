"""Structured concurrent fan-out.

``asyncio.gather`` leaves sibling tasks running after one fails, so a failed
page fetch keeps spending upstream requests whose results nobody will read.
``asyncio.TaskGroup`` cancels the siblings, but surfaces failures as an
``ExceptionGroup``, which would stop callers' ``except``/``pytest.raises``
(e.g. ``ToolError``, ``UpstreamError``) from matching. ``gather_all`` keeps
``gather``'s contract -- ordered results, the first failure re-raised as
itself -- and adds the cancellation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, overload


@overload
async def gather_all[A, B](
    a: Coroutine[Any, Any, A], b: Coroutine[Any, Any, B], /
) -> tuple[A, B]: ...
@overload
async def gather_all[T](*coros: Coroutine[Any, Any, T]) -> tuple[T, ...]: ...
async def gather_all(*coros: Coroutine[Any, Any, Any]) -> tuple[Any, ...]:
    """Run ``coros`` concurrently; return results in order.

    On the first failure the remaining tasks are cancelled and that failure is
    re-raised unwrapped.
    """
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(c) for c in coros]
    except ExceptionGroup as group:
        raise group.exceptions[0] from None
    return tuple(t.result() for t in tasks)
