"""Model eval: Haiku 5.5 / Sonnet 5.5 / Opus 5.5 answering FastAPI questions.

For each (model, condition, case, rep) it runs a real agent loop against the
production tool definitions (served by an in-process FastMCP client) and records
latency, tokens, cost and an outcome grade. Conditions:

* ``tools``    -- the 6 MCP tools available, told to ground answers in the docs
* ``baseline`` -- no tools (what the model knows from memory)

Methodology (see docs/EVAL.md): sequential trials per model (no local queueing),
cold server cache per trial, latency timed on the final successful attempt only
(client retries/backoff excluded), usage tokens straight from the API, served
model asserted on every response, infra failures kept out of results.jsonl.

Usage (needs ANTHROPIC_API_KEY or `ant auth login`):
    uv run --with anthropic python -m bench.eval.run_eval --out bench/eval/runs/r1
    uv run --with anthropic python -m bench.eval.run_eval --dry-run   # no API, no cost
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Any

import anthropic
from fastmcp import Client

from fastapi_docs_mcp import cache, http, mcp

from .cases import CASES, Case
from .grade import grade

MODELS = ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")
# $/MTok: (input, output, cache read). From the claude-api skill pricing table
# (cached 2026-10-06); Haiku's cache-read rate is assumed 0.1x input. Cache writes
# are billed at 1.25x input. Haiku 5.5 input >100K tokens costs more (never hit here).
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
}
SYSTEM = {
    "tools": (
        "You are a FastAPI documentation assistant. Use the provided tools to "
        "ground your answers in the official FastAPI docs; do not answer FastAPI "
        "questions from memory alone. If the question is not about FastAPI, say "
        "it is out of scope and do not call tools. Be concise."
    ),
    "baseline": "You are a FastAPI assistant. Be concise.",
}
MAX_TOKENS = 16000
MAX_TURNS = 8
MAX_ATTEMPTS = 5
TRIAL_TIMEOUT_S = 300.0
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


class ModelMismatchError(RuntimeError):
    """The response was served by a different model than requested."""


def cost_usd(model: str, usage: Any) -> float:
    """Dollar cost of one call from API-reported usage (incl. cache rates)."""
    p_in, p_out, p_cr = PRICES[model]
    cache_read = usage.cache_read_input_tokens or 0
    cache_write = usage.cache_creation_input_tokens or 0
    return (
        usage.input_tokens * p_in
        + usage.output_tokens * p_out
        + cache_read * p_cr
        + cache_write * p_in * 1.25
    ) / 1_000_000


async def model_call(
    client: anthropic.AsyncAnthropic,
    model: str,
    kwargs: dict[str, Any],
) -> tuple[Any, float | None, float, int]:
    """Stream one request; return (message, ttft_s, duration_s, attempts).

    ttft/duration time only the final (successful) attempt; backoff is excluded.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        ttft: float | None = None
        try:
            async with client.messages.stream(model=model, **kwargs) as stream:
                async for event in stream:
                    if ttft is None and event.type == "content_block_start":
                        ttft = time.perf_counter() - started
                final = await stream.get_final_message()
        except anthropic.APIConnectionError, anthropic.APITimeoutError:
            pass
        except anthropic.APIStatusError as exc:
            if exc.status_code not in RETRYABLE_STATUS:
                raise
        else:
            if final.model != model:
                msg = f"asked for {model}, served by {final.model}"
                raise ModelMismatchError(msg)
            return final, ttft, time.perf_counter() - started, attempt
        await asyncio.sleep(min(30.0, 2.0**attempt) * (0.5 + random.random()))  # noqa: S311
    msg = f"gave up after {MAX_ATTEMPTS} attempts"
    raise RuntimeError(msg)


async def run_tool(
    mcp_client: Client, block: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Execute one tool_use block; return (tool_result block, timing record)."""
    started = time.perf_counter()
    try:
        res = await mcp_client.call_tool(block.name, block.input, raise_on_error=False)
        text = "".join(b.text for b in res.content if hasattr(b, "text"))
        is_error = bool(res.is_error)
    except Exception as exc:
        text, is_error = f"tool call failed: {exc}", True
    dur = time.perf_counter() - started
    result = {
        "type": "tool_result",
        "tool_use_id": block.id,
        "content": text,
        "is_error": is_error,
    }
    return result, {
        "kind": "tool",
        "name": block.name,
        "dur_s": dur,
        "result_chars": len(text),
        "is_error": is_error,
    }


async def run_trial(
    client: anthropic.AsyncAnthropic,
    mcp_client: Client,
    tools: list[dict[str, Any]],
    model: str,
    condition: str,
    case: Case,
    rep: int,
    effort: str,
) -> dict[str, Any]:
    """Run one agent episode and return its result row."""
    cache.clear()  # cold server cache: worst-case, order-independent tool latency
    kwargs: dict[str, Any] = {
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM[condition],
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
    }
    if condition == "tools":
        kwargs["tools"] = tools
    messages: list[dict[str, Any]] = [{"role": "user", "content": case.question}]
    calls: list[dict[str, Any]] = []
    answer, status, tool_calls = "", "max_turns", []
    for _ in range(MAX_TURNS):
        final, ttft, dur, attempts = await model_call(
            client, model, {**kwargs, "messages": messages}
        )
        u = final.usage
        calls.append(
            {
                "kind": "model",
                "ttft_s": ttft,
                "dur_s": dur,
                "attempts": attempts,
                "stop_reason": final.stop_reason,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
                "cache_read": u.cache_read_input_tokens or 0,
                "cache_write": u.cache_creation_input_tokens or 0,
                "cost_usd": cost_usd(model, u),
            }
        )
        messages.append({"role": "assistant", "content": final.content})
        if final.stop_reason == "tool_use":
            blocks = [b for b in final.content if b.type == "tool_use"]
            phase = time.perf_counter()
            outcomes = await asyncio.gather(*(run_tool(mcp_client, b) for b in blocks))
            calls.extend(rec for _, rec in outcomes)
            tool_calls.extend(b.name for b in blocks)
            calls[
                -1 - len(blocks) + 1 :
            ]  # keep ordering: tools follow their model call
            messages.append({"role": "user", "content": [r for r, _ in outcomes]})
            calls.append({"kind": "tool_phase", "dur_s": time.perf_counter() - phase})
            continue
        answer = "".join(b.text for b in final.content if b.type == "text")
        status = {"max_tokens": "truncated", "refusal": "refusal"}.get(
            final.stop_reason, "ok"
        )
        break
    model_calls = [c for c in calls if c["kind"] == "model"]
    wall = sum(c["dur_s"] for c in model_calls) + sum(
        c["dur_s"] for c in calls if c["kind"] == "tool_phase"
    )
    return {
        "model": model,
        "condition": condition,
        "case": case.id,
        "tool": case.tool,
        "rep": rep,
        "status": status,
        "passed": status == "ok" and grade(case, answer, len(tool_calls)),
        "answer": answer,
        "tool_calls": tool_calls,
        "n_model_calls": len(model_calls),
        "wall_s": wall,
        "ttft_s": model_calls[0]["ttft_s"],
        "input_tokens": sum(c["input_tokens"] for c in model_calls),
        "output_tokens": sum(c["output_tokens"] for c in model_calls),
        "cost_usd": sum(c["cost_usd"] for c in model_calls),
        "calls": calls,
    }


def load_done(path: Path) -> set[tuple[str, str, str, int]]:
    """Keys of trials already in results.jsonl (resume support)."""
    if not path.exists():
        return set()
    rows = (json.loads(line) for line in path.read_text().splitlines() if line)
    return {(r["model"], r["condition"], r["case"], r["rep"]) for r in rows}


async def run_model(
    model: str,
    args: argparse.Namespace,
    ctx: dict[str, Any],
) -> None:
    """Run every pending trial for one model sequentially."""
    out: Path = args.out
    done = ctx["done"]
    plan = [
        (cond, case, rep)
        for cond in args.conditions
        for case in ctx["cases"]
        for rep in range(args.reps)
        if (model, cond, case.id, rep) not in done
    ]
    random.Random(f"{args.seed}-{model}").shuffle(plan)  # noqa: S311
    for cond, case, rep in plan:
        if ctx["spent"][0] >= args.max_cost:
            print(f"[{model}] cost cap ${args.max_cost} reached; stopping")
            return
        try:
            row = await asyncio.wait_for(
                run_trial(
                    ctx["client"],
                    ctx["mcp"],
                    ctx["tools"],
                    model,
                    cond,
                    case,
                    rep,
                    args.effort,
                ),
                TRIAL_TIMEOUT_S,
            )
        except Exception as exc:
            err = {
                "model": model, "condition": cond, "case": case.id, "rep": rep,
                "error": f"{type(exc).__name__}: {exc}",
            }  # fmt: skip
            with (out / "errors.jsonl").open("a") as fh:
                fh.write(json.dumps(err) + "\n")
            print(f"[{model}] ERROR {cond}/{case.id}/{rep}: {err['error'][:120]}")
            continue
        ctx["spent"][0] += row["cost_usd"]
        with (out / "results.jsonl").open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(
            f"[{model.split('-')[1]:6}] {cond:8} {case.id:20} r{rep} "
            f"{'PASS' if row['passed'] else 'fail'} {row['status']:9} "
            f"{row['wall_s']:5.1f}s calls={row['n_model_calls']} "
            f"${row['cost_usd']:.4f} (total ${ctx['spent'][0]:.2f})"
        )


async def main_async(args: argparse.Namespace) -> None:
    """Wire up clients and run all models concurrently (one worker each)."""
    logging.disable(logging.CRITICAL)
    args.out.mkdir(parents=True, exist_ok=True)
    cases = [c for c in CASES if not args.cases or c.id in args.cases]
    client_kwargs: dict[str, Any] = {"max_retries": 0, "timeout": 120.0}
    server = None
    if args.dry_run:
        from .fake_server import start

        server, base_url = start()
        client_kwargs.update(base_url=base_url, api_key="dry-run")
    client = anthropic.AsyncAnthropic(**client_kwargs)
    async with Client(mcp) as mcp_client:
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in await mcp_client.list_tools()
        ]
        ctx = {
            "client": client, "mcp": mcp_client, "tools": tools, "cases": cases,
            "done": load_done(args.out / "results.jsonl"), "spent": [0.0],
        }  # fmt: skip
        await asyncio.gather(*(run_model(m, args, ctx) for m in args.models))
    await client.close()
    await http.aclose()
    if server:
        server.shutdown()
    print(f"done. spent ${ctx['spent'][0]:.2f}. results in {args.out}")


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("bench/eval/runs/latest"))
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=MODELS)
    ap.add_argument("--conditions", nargs="+", default=["tools", "baseline"])
    ap.add_argument("--cases", nargs="*", help="case ids (default: all)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--max-cost", type=float, default=10.0, help="USD hard cap")
    ap.add_argument("--seed", default="eval-1")
    ap.add_argument("--dry-run", action="store_true", help="fake local API, no cost")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
