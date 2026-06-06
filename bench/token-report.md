# Token Utilization Report — v1 (HTML scrape) vs v2 (markdown + HTML fallback)

**Method:** [`bench/benchmark.py`](benchmark.py) runs each tool with a fixed input and
counts the returned payload in tokens via tiktoken `cl100k_base` (a deterministic
proxy for LLM tokenization). Absolute numbers are approximate; the BEFORE/AFTER
delta — same encoder, same inputs — is apples-to-apples. Raw captures:
[`before.json`](before.json), [`after.json`](after.json).

**Inputs:** `get_fastapi_docs("tutorial/first-steps")`, `search_fastapi_docs("cors")`,
`list_fastapi_pages()`, `get_fastapi_example("cors")`,
`compare_fastapi_approaches("auth-methods")`, `get_fastapi_best_practices("security")`.

## Results (tokens)

| Tool | Before | After | Δ tokens | Δ % |
|------|-------:|------:|---------:|----:|
| `get_fastapi_docs` | 2644 | 2490 | −154 | **−5.8%** |
| `search_fastapi_docs` | 1081 | 1221 | +140 | +13.0% |
| `list_fastapi_pages` | 844 | 844 | 0 | 0.0% |
| `get_fastapi_example` | 147 | 147 | 0 | 0.0% |
| `compare_fastapi_approaches` | 470 | 459 | −11 | −2.3% |
| `get_fastapi_best_practices` | 2753 | 2128 | −625 | **−22.7%** |
| **Total** | **7939** | **7289** | **−650** | **−8.2%** |

## Reading the numbers

- **Net −8.2%** across the suite, with **4 of 6 tools down or flat** and a large win
  on the heaviest tool (`get_fastapi_best_practices`, −22.7%).
- **Quality rose at the same time.** v1 leaked broken HTML into output — e.g.
  `get_fastapi_docs` previously contained `<font ...>`, `<span ...>`, `<u ...>`
  fragments from the docs site's terminal blocks. v2 emits clean markdown with real
  ```python fences and denoised console blocks. So tokens fell *and* signal rose.
- **`search_fastapi_docs` is +13% — and that is the good kind of increase.** v1's
  garbled scrape dropped/mangled the `CORSMiddleware` parameter reference
  (`allow_origins`, `allow_methods`, `allow_credentials`, `max_age`, …). v2 returns
  that reference intact. The extra ~140 tokens buy materially more-correct content
  that the prior version failed to deliver — exactly the carve-out in the design's
  acceptance gate. There was no remaining noise to trim on that page (verified by
  inspection); cutting further would mean discarding real reference material.

## What drove the reduction

1. **Markdown source instead of HTML scraping** — eliminates leftover-tag noise.
2. **Console/terminal blocks reduced to their command lines** — 40-line server boot
   logs (near-zero value to an assistant) collapse to `$ fastapi dev`.
3. **Image embeds dropped, link URLs stripped** (text kept) — pure token noise removed.
4. **Low-value config/schema dumps capped** (`json`/`toml`/text fences > 600 chars).
5. **`compare` code/summaries capped** to an illustrative head.

## Tool-definition tokens (sent on every request)

Tool *outputs* aren't the only token cost. The `tools` array — names + descriptions
+ JSON schemas — is re-sent as input on **every** request to the model (Anthropic and
OpenAI both bill this). Two independent levers were applied:

1. **Trimmed docstrings.** Following OpenAI's "reduce schema verbosity" and the
   "intern test", parameter descriptions were cut to 2–3 disambiguating examples and
   the redundant `Returns:` blocks dropped (FastMCP discards them anyway). Measured on
   the `name` + `description` + `inputSchema` triple (the part docstrings affect):

   | | Before | After | Δ |
   |---|---:|---:|----:|
   | All 6 tool definitions | 568 | 411 | **−27.6%** |

2. **`output_schema=None`.** A second, previously unmeasured cost: FastMCP auto-wraps
   every plain `-> str` return in a generated
   `{"result": {"type": "string"}, ..., "x-fastmcp-wrap-result": true}` schema and
   ships it in `tools/list` on **every** tool, in **every** request — a fixed
   ~29 tok/tool of pure overhead describing a type the description already states.
   Opting out (`@mcp.tool(..., output_schema=None)`) removes it from the wire payload
   with **no behavior change** — FastMCP still validates and wraps the return value
   internally; only the *advertised* schema shrinks. Measured on the full `tools/list`
   wire payload (`Tool.model_dump_json(exclude_none=True)`, the bytes actually billed):

   | | Default (`outputSchema` emitted) | `output_schema=None` | Δ |
   |---|---:|---:|----:|
   | All 6 tool definitions | 728 | 554 | **−174 (−23.9%)** |

Both stack: the full wire payload for this server's 6 tools is **554 tokens**. This is
a fixed per-request saving on top of the per-call output savings above. With prompt
caching it's cheaper still (the tool list is byte-stable — we never mutate it per
request — so it caches and re-reads at ~0.1×).

## FastMCP 3.2.4 → 3.4.2 upgrade

Re-ran the full output benchmark on the upgraded runtime (`fastmcp>=3.4.2,<3.5`):
**byte-identical tool outputs** (7,289 tokens total, unchanged — see
[`latest.json`](latest.json) vs [`after.json`](after.json)) and **byte-identical
`tools/list` wire format**, confirmed via an isolated `uv run --with fastmcp==3.2.4`
A/B re-serialization of the same tool definitions on both runtimes (122 / 138 tok per
tool, identical on both). The upgrade is a clean drop-in with **zero token impact**
either direction — it's a maintenance/feature update, not a token-format change. (The
`output_schema=None` win above was latent on 3.2.4 too; it just hadn't been measured
or applied yet — the prior 411-token figure used the narrower
name+description+inputSchema triple, which doesn't include `outputSchema`.)

## ⚠️ Token-count caveat

These counts use tiktoken (`cl100k_base`) as a **deterministic proxy**. Anthropic's
tokenizer differs — tiktoken **undercounts Claude tokens by ~15–20%**, so real Claude
costs run proportionally higher. The BEFORE/AFTER *ratios* hold regardless of
tokenizer. For exact Claude counts use the `count_tokens` API, not tiktoken. The cost
analysis in [`../docs/MODEL-COST-ANALYSIS.md`](../docs/MODEL-COST-ANALYSIS.md) applies a
×1.2 adjustment to approximate Claude tokens.

## Reproduce

```bash
uv run --with tiktoken python bench/benchmark.py before > bench/before.json  # on v1
uv run --with tiktoken python bench/benchmark.py after  > bench/after.json   # on v2
```
