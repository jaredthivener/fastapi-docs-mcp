#!/usr/bin/env python
"""Accuracy, latency and cost of Claude models answering FastAPI questions.

Each question is asked with this server's tools ("tools") and without ("baseline").
Latency is wall time for the whole episode (model + tool calls); TTFT is the first
streamed content block of the first call. Server cache is cleared per question.

Usage (needs ANTHROPIC_API_KEY):
    uv run --with anthropic python bench/model_eval.py [reps]
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

import anthropic
from fastmcp import Client

from fastapi_docs_mcp import cache, http, mcp

# $/MTok (input, output), claude-api skill pricing table (2026-10-06).
MODELS = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
MAX_COST = 10.0  # USD; stop issuing questions past this
# (question, substrings that must all appear in the answer); facts from the live docs.
CASES = [
    (
        "In FastAPI's first-steps tutorial, which command starts the dev server?",
        ["fastapi dev"],
    ),
    (
        "Enable CORS in FastAPI: name the middleware class and origins option.",
        ["corsmiddleware", "allow_origins"],
    ),
    (
        "How do I run work after returning a response in FastAPI?",
        ["backgroundtasks", "add_task"],
    ),
    (
        "Which FastAPI docs page covers Docker deployment? Give its path.",
        ["deployment/docker"],
    ),
    ("Show a minimal FastAPI WebSocket echo example.", ["websocket", "receive_text"]),
    (
        "When should I use async def vs def for FastAPI path operations?",
        ["async def", "await"],
    ),
]
SYSTEM = {
    "tools": "Answer using the FastAPI docs tools rather than memory. Be concise.",
    "baseline": "Answer FastAPI questions concisely.",
}
spent = 0.0


async def ask(client, mcp_client, tools, model, cond, question):  # type: ignore[no-untyped-def]
    """Run one episode; return (answer, wall_s, ttft_s, cost_usd)."""
    global spent  # noqa: PLW0603
    cache.clear()
    kw = {"tools": tools} if cond == "tools" else {}
    messages = [{"role": "user", "content": question}]
    start, ttft, cost = time.perf_counter(), None, 0.0
    while True:
        async with client.messages.stream(
            model=model, max_tokens=16000, system=SYSTEM[cond], messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": "medium"}, **kw,
        ) as stream:  # fmt: skip
            async for ev in stream:
                if ttft is None and ev.type == "content_block_start":
                    ttft = time.perf_counter() - start
            msg = await stream.get_final_message()
        assert msg.model == model, f"served by {msg.model}"
        cost += (
            msg.usage.input_tokens * MODELS[model][0]
            + msg.usage.output_tokens * MODELS[model][1]
        ) / 1e6
        messages.append({"role": "assistant", "content": msg.content})
        if msg.stop_reason != "tool_use":
            break
        results = []
        for b in (b for b in msg.content if b.type == "tool_use"):
            r = await mcp_client.call_tool(b.name, b.input, raise_on_error=False)
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": text,
                    "is_error": r.is_error,
                }
            )
        messages.append({"role": "user", "content": results})
    spent += cost
    answer = "".join(b.text for b in msg.content if b.type == "text")
    return answer, time.perf_counter() - start, ttft, cost


async def run_model(client, mcp_client, tools, model, reps):  # type: ignore[no-untyped-def]
    """All trials for one model, sequentially: {cond: [(ok, wall, ttft, cost)]}."""
    out: dict[str, list] = {"tools": [], "baseline": []}  # type: ignore[type-arg]
    for _ in range(reps):
        for question, facts in CASES:
            for cond in out:
                if spent >= MAX_COST:
                    return out
                answer, wall, ttft, cost = await ask(
                    client, mcp_client, tools, model, cond, question
                )
                out[cond].append(
                    (all(f in answer.lower() for f in facts), wall, ttft, cost)
                )
    return out


async def main() -> None:
    """Run every model concurrently and print one summary table."""
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    client = anthropic.AsyncAnthropic(max_retries=0)
    async with Client(mcp) as mcp_client:
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.input_schema,
            }
            for t in await mcp_client.list_tools()
        ]
        results = await asyncio.gather(
            *(run_model(client, mcp_client, tools, m, reps) for m in MODELS)
        )
    await http.aclose()
    cols = ("model", "cond", "n", "pass", "wall p50", "wall max", "ttft p50", "$/q")
    print(f"{cols[0]:20}{cols[1]:10}" + "".join(f"{c:>10}" for c in cols[2:]))
    for model, res in zip(MODELS, results, strict=True):
        for cond, rows in res.items():
            if rows:
                ok, wall, ttft, cost = zip(*rows, strict=True)
                print(
                    f"{model:20}{cond:10}{len(rows):>4}{sum(ok) / len(ok):>7.0%}"
                    f"{statistics.median(wall):>9.1f}s{max(wall):>9.1f}s{statistics.median(ttft):>9.2f}s"
                    f"{statistics.mean(cost):>9.4f}"
                )
    print(f"total spent ${spent:.2f}")


if __name__ == "__main__":
    asyncio.run(main())
