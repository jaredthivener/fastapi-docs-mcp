"""Summarise an eval run (results.jsonl + errors.jsonl) as markdown tables.

Usage: uv run python -m bench.eval.report bench/eval/runs/r1 > report.md
Every number is recomputed from the raw per-trial rows.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def pct(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100); nan for an empty list."""
    if not values:
        return math.nan
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q / 100 * len(ordered)) - 1)]


def wilson(passed: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a pass rate."""
    if n == 0:
        return math.nan, math.nan
    z, p = 1.96, passed / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def mean(values: list[float]) -> float:
    """Arithmetic mean; nan for an empty list."""
    return sum(values) / len(values) if values else math.nan


def load(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file (missing file -> empty)."""
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def summary_table(rows: list[dict[str, Any]]) -> list[str]:
    """Per (model, condition) quality, latency, tokens and cost."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["condition"])].append(r)
    out = [
        "| model | condition | n | pass (95% CI) | wall p50 | wall p95 | TTFT p50 "
        "| model calls | tool calls | in tok | out tok | $/question |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for (model, cond), g in sorted(groups.items()):
        n, ok = len(g), sum(r["passed"] for r in g)
        lo, hi = wilson(ok, n)
        wall = [r["wall_s"] for r in g]
        out.append(
            f"| {model} | {cond} | {n} | {ok / n:.0%} ({lo:.0%}-{hi:.0%}) "
            f"| {pct(wall, 50):.1f}s | {pct(wall, 95):.1f}s "
            f"| {pct([r['ttft_s'] for r in g if r['ttft_s'] is not None], 50):.2f}s "
            f"| {mean([r['n_model_calls'] for r in g]):.1f} "
            f"| {mean([len(r['tool_calls']) for r in g]):.1f} "
            f"| {mean([r['input_tokens'] for r in g]):,.0f} "
            f"| {mean([r['output_tokens'] for r in g]):,.0f} "
            f"| ${mean([r['cost_usd'] for r in g]):.4f} |"
        )
    return out


def by_tool_table(rows: list[dict[str, Any]]) -> list[str]:
    """Pass rate by the server tool each case targets, tools vs baseline."""
    cells: dict[tuple[str, str, str], list[bool]] = defaultdict(list)
    for r in rows:
        cells[(r["tool"], r["model"], r["condition"])].append(r["passed"])
    models = sorted({r["model"] for r in rows})
    out = [
        "| case target | " + " | ".join(f"{m} tools / base" for m in models) + " |",
        "|---|" + "---|" * len(models),
    ]
    for tool in sorted({r["tool"] for r in rows}):
        parts = []
        for m in models:
            t, b = cells[(tool, m, "tools")], cells[(tool, m, "baseline")]
            parts.append(
                f"{mean([float(x) for x in t]):.0%} / {mean([float(x) for x in b]):.0%}"
            )
        out.append(f"| {tool} | " + " | ".join(parts) + " |")
    return out


def server_latency_table(rows: list[dict[str, Any]]) -> list[str]:
    """Server-side tool latency (cold cache), independent of the model."""
    lat: dict[str, list[float]] = defaultdict(list)
    size: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for c in r["calls"]:
            if c["kind"] == "tool":
                lat[c["name"]].append(c["dur_s"])
                size[c["name"]].append(c["result_chars"])
    out = [
        "| tool | calls | p50 | p95 | mean result chars |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in sorted(lat):
        out.append(
            f"| {name} | {len(lat[name])} | {pct(lat[name], 50) * 1000:.0f} ms "
            f"| {pct(lat[name], 95) * 1000:.0f} ms | {mean(size[name]):,.0f} |"
        )
    return out


def main(run_dir: Path) -> None:
    """Print the full markdown report for ``run_dir``."""
    rows, errors = load(run_dir / "results.jsonl"), load(run_dir / "errors.jsonl")
    if not rows:
        print("no results")
        return
    odd = defaultdict(int)
    for r in rows:
        if r["status"] != "ok":
            odd[(r["model"], r["status"])] += 1
    print(f"# Eval report: {run_dir}\n")
    print(f"{len(rows)} graded trials, {len(errors)} infra errors (excluded).\n")
    print("## Quality, latency, cost\n")
    print("\n".join(summary_table(rows)))
    print("\n## Pass rate by case target (tools / baseline)\n")
    print("\n".join(by_tool_table(rows)))
    print("\n## Server tool latency (cold cache)\n")
    print("\n".join(server_latency_table(rows)))
    if odd:
        print("\n## Non-ok statuses (counted as not passed)\n")
        for (m, s), n in sorted(odd.items()):
            print(f"- {m}: {n} {s}")
    for e in errors[:10]:
        print(f"- error {e['model']}/{e['condition']}/{e['case']}: {e['error'][:100]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
