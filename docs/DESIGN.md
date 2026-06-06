# Design — FastAPI Docs MCP Server

> Architecture and rationale for the optimized server. Companion to the
> implementation plan in [`tasks/todo.md`](../tasks/todo.md) and the measured
> token results in [`bench/token-report.md`](../bench/token-report.md).

## 1. Purpose

An MCP server exposing six read-only tools that let an AI assistant query
**live FastAPI documentation**. The server is the trust boundary between the
assistant and two upstream sources (the docs site and the FastAPI GitHub repo);
its job is to fetch, clean, and **token-efficiently** present documentation.

## 2. Design principles

1. **Dynamic discovery, never breaks on upstream change.** The sitemap is the
   single runtime source of truth for which pages exist. No page inventory is
   hardcoded. New/renamed docs are discovered automatically.
2. **Optimize acquisition, not discovery.** *How* content is fetched may be
   optimized aggressively; *what* is discoverable must stay driven by the sitemap.
3. **Couple to the public contract, not implementation details.** Sitemap site
   URLs are stable; the GitHub repo's internal layout and include syntax are not
   (the include macro already changed `{!...!}` → `{* *}`). So GitHub is the
   *preferred* source but never the *only* source.
4. **Token efficiency is a first-class requirement.** Every byte returned is a
   token the assistant pays for. Strip noise; prefer structured markdown; honor
   the docs' own line-slices for code.
5. **Fail soft.** Tools return helpful guidance text instead of raising, so the
   assistant can recover.

## 3. High-level architecture

```
                    ┌──────────────────────────────┐
   MCP client ──────▶  server.py  (FastMCP, stdio) │
                    └───────────────┬──────────────┘
                                    │  6 @mcp.tool fns
                            ┌───────▼────────┐
                            │    tools.py    │  thin orchestration
                            └───┬────────┬───┘
                  discovery     │        │   content acquisition
                        ┌───────▼──┐  ┌──▼──────────┐
                        │sitemap.py│  │ content.py  │  fetch_content(path):
                        └────┬─────┘  └──┬───────┬──┘   markdown → HTML fallback
                             │           │       │
                             │     ┌─────▼──┐ ┌──▼─────┐
                             │     │markdown│ │ html.py│ (lean fallback extractor)
                             │     └────┬───┘ └───┬────┘
                             └──────────┴─────────┴──────────┐
                                              ┌──────────────▼─┐
                                              │     http.py    │ shared client,
                                              │   + cache.py   │ TTL/LRU/single-flight
                                              └────────────────┘
```

### Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `config.py` | All constants: URLs, host allowlist, timeouts, size caps, TTLs, limits. |
| `http.py` | Shared `httpx.AsyncClient` (pooled, keep-alive); host-allowlisted, size-capped GET; integrates cache + single-flight. The **only** place network I/O happens. |
| `cache.py` | TTL cache with LRU bound + per-key `asyncio.Lock` (single-flight). |
| `sitemap.py` | **Discovery**: fetch/parse sitemap, keyword-alias search, categorization. |
| `markdown.py` | Path→raw-md URL resolution, `{* *}`/`{!!}` include resolution (with `ln[]` slicing), MkDocs cleanup, truncation. |
| `html.py` | Lean HTML→text/code extractor — the resilience fallback only. |
| `content.py` | `fetch_content(path)`: markdown-preferred → HTML fallback seam. |
| `tools.py` | The six `@mcp.tool` functions. Pure orchestration. |
| `server.py` | FastMCP instance, stderr logging, client lifespan, `mcp.run()`. |
| `main.py` | Thin entrypoint shim re-exporting the public API (keeps Docker/mcp.json/tests stable). |

## 4. Content acquisition (the core optimization)

### 4.1 Source mapping (validated live)
- Sitemap path `p` → markdown candidates, first hit wins:
  `…/docs/en/docs/{p}.md`, then `…/docs/en/docs/{p}/index.md`, then `index.md`.
- Python examples are **not inline**; they are include directives:
  `{* ../../docs_src/<sub>/<file>.py ln[a:b] hl[…] *}` (legacy `{!…!}`).
  `docs_src/` lives at the **repo root**, so an include is resolved by taking the
  substring from `docs_src/` onward and prefixing the repo raw root. Resilient to
  the directive's relative depth.

### 4.2 Markdown pipeline
1. `fetch_markdown(path)` — resolve candidate, fetch via `http.py`.
2. `resolve_includes(md)` — for each directive: fetch the `docs_src` file (parallel,
   cached, count/size-capped); if `ln[a:b]` present, inline only that slice; emit a
   fenced ```python block. On fetch failure, leave a readable placeholder, not the
   raw directive.
3. `clean_mkdocs(md)` — strip `{ #anchor }` heading suffixes; convert `/// note|tip|
   warning …` admonitions to `**Label:**` lead-ins; strip `<font>/<span>/<div>` HTML
   noise from `termy` console blocks; normalize whitespace.
4. `truncate_content(md)` — paragraph-aware cut at `MAX_CONTENT_LENGTH`.

### 4.3 Fallback seam
`content.fetch_content(path)` returns markdown when steps above yield non-empty
cleaned text; otherwise it transparently falls back to `html.py` extraction of the
live sitemap URL. Guarantees: **any sitemap-discoverable page is always served**,
even if the repo reorganizes or the include macro changes again.

## 5. Cross-cutting concerns

### 5.1 HTTP & performance
- One pooled `AsyncClient` with keep-alive replaces the per-request client
  (connection reuse across the many fetches the parallel tools issue).
- The client is **loop-aware**: recreated if the running event loop changes
  (so pytest's function-scoped loops don't reuse a closed-loop client) — one
  client per loop, reused within it.
- Cache TTL raised to hours (docs are near-static); LRU-bounded; single-flight
  collapses concurrent misses into one upstream fetch.

### 5.2 Security
- **Host allowlist** (`fastapi.tiangolo.com`, `raw.githubusercontent.com`),
  enforced on the *final* URL after redirects.
- **Size-capped streamed download** bounds memory before `.text`.
- **Input validation** on tool args: length cap, control-char strip, reject
  scheme/host/`..`-traversal injection in `path`.
- Logging is configured to **stderr** (stdout is the MCP stdio channel).

### 5.3 MCP conformance
- All six tools annotated `readOnlyHint=True`, `openWorldHint=True`.
- Explicit stdio transport. Tools return guidance strings, never exceptions.

## 6. Acceptance gate

The redesign is accepted only if it **strictly improves token utilization**
(measured per-tool and in aggregate by `bench/benchmark.py`) **and** does not
regress any other axis (security, performance, maintainability, MCP conformance,
test coverage ≥90%). Where a tool's raw token count rises, it must be because it
now returns substantively more-correct content that the prior version failed to
deliver (e.g. real code examples), documented in the token report.

## 7. Alternatives considered

| Option | Why not (as primary) |
|--------|----------------------|
| HTML-only (status quo) | Fragile regex, leftover-tag noise inflates tokens, flattens structure. Kept as fallback. |
| Markdown-only (hard cutover) | Couples to repo internals; breaks the "never breaks" principle. Rejected in favor of fallback seam. |
| Full HTML parser dep (selectolax) | Adds a C dependency; still HTML-noise-bound; markdown source is cleaner at the root. |
| `htmltomarkdown`/readability libs | Heavier deps for a problem the upstream markdown source already solves. |
