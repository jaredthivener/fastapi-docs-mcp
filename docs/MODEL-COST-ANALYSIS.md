# Model Cost Analysis — "Best Bang for the Buck" per Tool Call

Which model should a user run their MCP client on when calling these six tools?
This server is model-agnostic — the **client** model (Claude, GPT, …) decides when to
call a tool and pays for the tokens. This doc compares the per-call cost across the
Claude tiers and gives a per-tool recommendation.

> **Token caveat.** Output sizes come from [`../bench/benchmark.py`](../bench/benchmark.py)
> measured with tiktoken, which **undercounts Claude tokens by ~15–20%**. All Claude
> figures below apply a **×1.2** adjustment to approximate real Claude tokens. They are
> estimates for *relative comparison*; for exact billing use the `count_tokens` API.
> Verified against official pricing/overhead (cached 2026-05-26 via the claude-api skill).

## 1. What a tool call actually costs

A single "ask → tool call → answer" round trip bills three things:

| Component | Billed as | Who controls it |
|---|---|---|
| **Fixed overhead** — tool-use system prompt + the 6 tool definitions + user turn | input | the server (tool defs) + client |
| **Tool output** fed back to the model | input | **this server** (the optimization target) |
| **Generation** — the model's synthesized answer | output | the task, not the tool |

The server controls the first two. The full `tools/list` wire payload — what's
actually billed as fixed overhead — is **554 tok** (≈ 665 Claude tok) after trimming
docstrings *and* opting out of FastMCP's auto-generated `outputSchema` wrapper
(`output_schema=None`, −174 tok / −23.9% on top of the docstring win), and outputs are
cut **−8.2%** overall — see [`../bench/token-report.md`](../bench/token-report.md).

## 2. Pricing & per-request overhead (official)

| Model | Input $/1M | Output $/1M | Tool-use sys-prompt overhead (input tok) |
|---|---:|---:|---:|
| Claude Opus 4.8 | $5.00 | $25.00 | 290 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | 497 |
| Claude Haiku 4.5 | $1.00 | $5.00 | 496 |

Prompt caching: cache **write** 1.25× (5-min) / 2× (1h); cache **read ~0.1×** input.

## 3. Per-tool cost — the tool output consumed as input

Output tokens (×1.2 Claude-adjusted) and the input cost of feeding that output back,
**per 1,000 calls**:

| Tool | Claude tok (est.) | Opus 4.8 | Sonnet 4.6 | Haiku 4.5 |
|---|---:|---:|---:|---:|
| `get_fastapi_example` | 176 | $0.88 | $0.53 | **$0.18** |
| `compare_fastapi_approaches` | 551 | $2.76 | $1.65 | **$0.55** |
| `list_fastapi_pages` | 1,013 | $5.07 | $3.04 | **$1.01** |
| `search_fastapi_docs` | 1,465 | $7.33 | $4.40 | **$1.47** |
| `get_fastapi_best_practices` | 2,554 | $12.77 | $7.66 | **$2.55** |
| `get_fastapi_docs` | 2,988 | $14.94 | $8.96 | **$2.99** |

(Input-side only. Haiku is **5×** cheaper than Opus for the identical payload.)

## 4. Representative full round trip

"Ask a question → one tool call → ~400-token answer." Fixed overhead = sys-prompt +
~665 tok tool defs (554 × 1.2 Claude-adjusted) + ~30 tok question. Example tool:
`search_fastapi_docs` (1,465 tok output). **First call** (cold cache) vs **cached**
(tool defs + sys-prompt at 0.1×):

| Model | Input tok | + Output | Cost / call (cold) | Cost / call (cached defs) |
|---|---:|---:|---:|---:|
| Opus 4.8 | ~2,450 | 400 | ~$0.0222 | ~$0.0178 |
| Sonnet 4.6 | ~2,657 | 400 | ~$0.0140 | ~$0.0108 |
| Haiku 4.5 | ~2,656 | 400 | **~$0.0047** | **~$0.0036** |

Caching matters because this server keeps the tool list **byte-stable** (never mutated
per request), so it's a clean cacheable prefix.

## 5. Recommendation — best bang for the buck

These six tools **fetch documentation the model then reads and relays**. That's a
low-reasoning, high-I/O task — exactly where the cheapest capable tier wins. Reserve
expensive reasoning models for the *surrounding* work, not the lookup.

| Use case | Recommended model | Why |
|---|---|---|
| **Default / high-volume doc lookup** (`get_fastapi_docs`, `search`, `list`, `example`) | **Haiku 4.5** | Read-and-relay needs no deep reasoning; 5× cheaper than Opus, fast. Best $/call. |
| **Synthesis across pages** (`get_fastapi_best_practices`, `compare`) | **Sonnet 4.6** | Light multi-page synthesis benefits from a step up; still 1.7× cheaper than Opus. |
| **Inside a complex coding/agent task** | **Opus 4.8** | If the surrounding task already runs on Opus, keep one model — switching mid-session breaks the prompt cache. Don't downgrade just for the lookup. |

**Rules of thumb**
- **Pick the model for the task, not the tool.** A doc fetch embedded in an Opus coding
  session should stay on Opus (cache continuity); a standalone "what's the CORS setup?"
  bot should run on Haiku.
- **Turn on prompt caching.** The tool definitions + system prompt are stable; caching
  re-reads them at ~0.1×, and the win compounds across a session.
- **Batch, non-interactive doc indexing?** The Batches API is 50% off — pair it with Haiku.

## 6. Cross-provider note

The same logic generalizes: these are "small/fast tier" tasks. On OpenAI, route them to
the economy/mini tier rather than the flagship; the read-relay nature means the cheap
tier is rarely the bottleneck. (Exact OpenAI/Gemini prices change often — confirm
against each provider's current pricing page; this analysis uses Claude's published
rates.) OpenAI's own guidance reinforces the design here: **<20 tools** (we have 6),
**concise schemas** (tool defs trimmed 27.6%), and **compact results** (outputs −8.2%).
