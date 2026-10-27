#!/usr/bin/env python
"""Accuracy, latency and cost of Claude models answering FastAPI questions.

Drives headless Claude Code (`claude -p`), so it runs on a Claude subscription, no
API key. Each question is asked with this server's tools ("tools") and without
("baseline"); built-in Claude Code tools are off and the system prompt is replaced,
so the only difference between conditions is this server. Every question is a fresh
process, so the server cache is always cold. Cost is Claude Code's list-price
estimate (not billed on a subscription).

Usage: uv run python bench/model_eval.py [reps]
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
# (question, substrings that must all appear in the answer); facts from the live docs.
CASES = [
    ("In FastAPI's first-steps tutorial, which command starts the dev server?",
     ["fastapi dev"]),
    ("Enable CORS in FastAPI: name the middleware class and origins option.",
     ["corsmiddleware", "allow_origins"]),
    ("How do I run work after returning a response in FastAPI?",
     ["backgroundtasks", "add_task"]),
    ("Which FastAPI docs page covers Docker deployment? Give its path.",
     ["deployment/docker"]),
    ("Show a minimal FastAPI WebSocket echo example.",
     ["websocket", "receive_text"]),
    ("When should I use async def vs def for FastAPI path operations?",
     ["async def", "await"]),
]  # fmt: skip
SYSTEM = {
    "tools": "Answer using the FastAPI docs tools rather than memory. Be concise.",
    "baseline": "Answer FastAPI questions concisely.",
}


def ask(model: str, cond: str, question: str, mcp_config: Path) -> dict:  # type: ignore[type-arg]
    """Run one headless episode and return Claude Code's JSON result."""
    cmd = [
        "claude", "-p", question, "--model", model, "--effort", "medium",
        "--output-format", "json", "--system-prompt", SYSTEM[cond], "--tools", "",
        "--strict-mcp-config", "--mcp-config", str(mcp_config),
        "--allowedTools", "mcp__fastapi-docs", "--setting-sources", "",
        "--disable-slash-commands", "--no-session-persistence",
    ]  # fmt: skip
    out = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        cwd=tempfile.gettempdir(),
    )
    return json.loads(out.stdout)  # type: ignore[no-any-return]


def run_model(model: str, reps: int, configs: dict[str, Path]) -> dict[str, list]:  # type: ignore[type-arg]
    """All trials for one model: {cond: [(ok, ms, ttft_ms, turns, usd)]}."""
    rows: dict[str, list] = {"tools": [], "baseline": [], "errors": []}  # type: ignore[type-arg]
    for _ in range(reps):
        for question, facts in CASES:
            for cond in ("tools", "baseline"):
                d = ask(model, cond, question, configs[cond])
                if d["is_error"] or model not in d["modelUsage"]:
                    rows["errors"].append((cond, question))
                    continue
                ok = all(f in d["result"].lower() for f in facts)
                rows[cond].append(
                    (
                        ok,
                        d["duration_ms"],
                        d["ttft_ms"],
                        d["num_turns"],
                        d["total_cost_usd"],
                    )
                )
    return rows


def main() -> None:
    """Run every model in parallel and print one summary table."""
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    tmp = Path(tempfile.mkdtemp())
    server = {
        "command": "uv",
        "args": ["run", "--directory", str(ROOT), "fastapi-docs-mcp"],
    }
    configs = {"tools": tmp / "tools.json", "baseline": tmp / "baseline.json"}
    configs["tools"].write_text(json.dumps({"mcpServers": {"fastapi-docs": server}}))
    configs["baseline"].write_text('{"mcpServers": {}}')
    with ThreadPoolExecutor(len(MODELS)) as pool:
        results = list(pool.map(lambda m: run_model(m, reps, configs), MODELS))
    cols = ("model", "cond", "n", "pass", "p50 s", "max s", "ttft p50", "turns", "$/q")
    print(f"{cols[0]:20}{cols[1]:10}" + "".join(f"{c:>9}" for c in cols[2:]))
    for model, res in zip(MODELS, results, strict=True):
        for cond in ("tools", "baseline"):
            if rows := res[cond]:
                ok, ms, ttft, turns, usd = zip(*rows, strict=True)
                print(
                    f"{model:20}{cond:10}{len(rows):>9}{sum(ok) / len(ok):>9.0%}"
                    f"{statistics.median(ms) / 1000:>9.1f}{max(ms) / 1000:>9.1f}"
                    f"{statistics.median(ttft) / 1000:>9.2f}"
                    f"{statistics.mean(turns):>9.1f}{statistics.mean(usd):>9.4f}"
                )
        if res["errors"]:
            print(f"  {model}: {len(res['errors'])} errored trials excluded")


if __name__ == "__main__":
    main()
