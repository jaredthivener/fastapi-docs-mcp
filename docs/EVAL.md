# Model eval — Haiku 5.5 / Sonnet 5.5 / Opus 5.5

Measures how well and how fast each model answers FastAPI questions **with** this
server's tools versus **without** them (model memory only), using the production
tool definitions via an in-process FastMCP client.

## Run it

```bash
export ANTHROPIC_API_KEY=...        # or: ant auth login
# 1. Free self-tests (no API cost): oracle passes, null fails, pipeline works
uv run python -m bench.eval.verify_oracle
uv run --with anthropic python -m bench.eval.run_eval --dry-run --out /tmp/dry --reps 1
# 2. Real smoke test (~$0.05): proves the live API parameters are accepted
uv run --with anthropic python -m bench.eval.run_eval --out bench/eval/runs/smoke \
    --cases docs-first-steps --reps 1
# 3. Full run (est. $3-6, hard-capped at --max-cost, default $10; resumable)
uv run --with anthropic python -m bench.eval.run_eval --out bench/eval/runs/r1
# 4. Report (recomputed from raw rows)
uv run python -m bench.eval.report bench/eval/runs/r1 > bench/eval/runs/r1/report.md
```

20 cases (3 per tool + 2 off-scope) x 3 models x {tools, baseline} x 3 reps = 360 trials.

## Method

- **Outcome grading**: every fact group needs one alternative (case-insensitive
  substring) in the answer. Gold comes from the live docs, not from a model;
  `verify_oracle.py` proves each case's oracle tool output passes and empty / "I
  don't know" answers fail. Off-scope cases pass only with zero tool calls.
- **Latency**: wall time = sum of final-successful-attempt model durations +
  tool phases. Client retries and backoff are excluded; attempts are recorded.
  TTFT = first `content_block_start` of the first model call (may be a thinking
  block). Server tool latency is timed separately from model latency.
- **Isolation**: server cache cleared before every trial (cold, worst case,
  order-independent). One worker per model, trials sequential within a model,
  order shuffled with a fixed seed.
- **Accounting**: tokens from API `usage`; cost from per-model rates (Haiku
  cache-read rate assumed 0.1x input; no prompt caching is used, so cache columns
  are ~0). Served model is asserted equal to the requested model on every response.
- **Failures**: infra errors / timeouts go to `errors.jsonl`, never scored as
  model failures. `max_tokens` and refusals are recorded as their own statuses.
- **Config**: adaptive thinking, `effort=medium` for all models (Opus 5.5 / Haiku
  5.5 default is medium, Sonnet 5.5's is high, so set explicitly), `max_tokens`
  16000, streaming, `tool_choice` auto (forced tool use is a 400 on these models).

## Known limitations

- FastAPI is well known to every model, so many cases are **answerable from
  memory**; the baseline column measures exactly that. The tools' advantage shows
  up mostly in latency/cost trade-offs and on version-specific details.
- Substring grading can miss a correct answer phrased differently (and cannot
  catch an incorrect extra claim). 20 cases x 3 reps gives roughly +/-10 points of
  noise on a pass rate; differences smaller than the reported CI are not signal.
- System prompts differ between conditions (tools: "ground in the docs";
  baseline: plain), which is the realistic deployment but not a pure ablation.
- Concurrent model workers share one machine/network, and the docs hosts are
  live: tool latency varies with GitHub/FastAPI site conditions.

## Pre-flight findings (measured with no model, before any paid run)

1. **`search_fastapi_docs` fails on multi-word queries.** It matches the whole
   query as a substring of the sitemap URL, so only exact aliases or single words
   work. On 25 natural queries the hit rate was **9/25 (36%)**: "static files",
   "background tasks", "path parameters", "request body", "sql databases", "file
   uploads", "error handling", "docker deployment", ... all returned "No results".
   An agent must recover via `list_fastapi_pages` (extra round trip + tokens).
2. **`list_fastapi_pages` truncates each section** ("... and 21 more"), so pages
   like `tutorial/testing` are not discoverable through it despite the tool's
   description saying it lists every page.
3. Tool output sizes vary widely (e.g. `get_fastapi_example("jwt")` returns ~17K
   characters, `("cors")` ~0.6K), so per-call token cost depends on the topic.
