# FastAPI Docs MCP — Optimization Plan

Status: **PROPOSED — awaiting approval before implementation**
Owner: Claude
Goals: security · performance · maintainability · token utilization · MCP best practices

## Non-negotiable design principle (carried from current architecture)
**Dynamic discovery, zero hardcoded page inventory, never breaks on new/moved upstream content.**
The sitemap remains the single runtime source of truth for what pages exist; new docs the maintainer
publishes are auto-discovered. No change below may regress this. Content *fetching* may be optimized, but
every page reachable via the sitemap must remain reachable.

## Decisions locked in (from review session)
- **Content source:** **markdown-preferred with HTML fallback** (revised). Prefer raw markdown from the
  FastAPI GitHub repo for token quality; **fall back to live-site HTML scraping** whenever the md path
  doesn't resolve, include syntax drifts, or cleanup fails. This keeps the "never breaks" guarantee:
  the GitHub repo's internal layout/include-syntax is an implementation detail (already changed once:
  `{!...!}` → `{* *}`), whereas the sitemap site URLs are the stable public contract.
- **Structure:** **modularize** `main.py` into a small package.
- **Scope:** this document only; no code changes until approved.

## Validated assumptions (probed live)
- Sitemap path → markdown URL mapping is real:
  `https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/<path>.md`
- Section roots / empty path map to `index.md` (e.g. `tutorial/` → `tutorial/index.md`, `/` → `index.md`).
  Rule: try `<path>.md`, then fall back to `<path>/index.md` (cache the resolved variant).
- **Wrinkle:** Python examples are NOT inline. They are include directives:
  `{* ../../docs_src/first_steps/tutorial001_py310.py *}` (legacy form: `{!../../...!}`).
  Real code requires resolving the include by fetching the referenced `docs_src/<...>.py` file.
- Markdown also carries minor MkDocs noise: `{ #anchor }` heading suffixes, `<div class="termy">`
  console blocks with HTML/font tags, and `///` admonition blocks.

---

## Target architecture

```
src/fastapi_docs_mcp/
  __init__.py
  config.py     # constants: base URLs, timeouts, limits, TTLs, allowlist
  http.py       # shared AsyncClient (pool + HTTP/2), streamed size-capped GET, host allowlist
  cache.py      # TTL cache: bounded (LRU) + single-flight lock to prevent stampede
  sitemap.py    # fetch_sitemap, _search_sitemap_urls, categorize_urls, alias map  (DISCOVERY — unchanged)
  markdown.py   # path→md-URL resolution, include resolution, MkDocs cleanup, truncation
  html.py       # lean HTML extractor — kept as the resilience fallback (slimmed from today's regex)
  content.py    # fetch_content(path): markdown-preferred → HTML fallback chain (the "never breaks" seam)
  tools.py      # the 6 @mcp.tool functions (thin orchestration over the above)
  server.py     # FastMCP instance, logging→stderr, lifespan (client open/close), mcp.run()
main.py         # thin shim: `from fastapi_docs_mcp.server import mcp; mcp.run()` (keeps Docker/mcp.json stable)
```
Keep `main.py` as the entrypoint so `Dockerfile`, `.vscode/mcp.json`, and CI need no path changes.
Update `pyproject.toml` `[tool.hatch.build.targets.wheel]` to package `src/fastapi_docs_mcp` + `main.py`,
and `[tool.ruff.lint.isort] known-first-party` accordingly.

---

## P0 — high impact, low risk

- [ ] **Shared `httpx.AsyncClient`** (replaces per-request client at current `main.py:116`).
  Module-level singleton with `httpx.Limits` (pool + keepalive), `http2=True`, `follow_redirects` controlled.
  Opened/closed via FastMCP **lifespan**; fall back to `atexit`-closed lazy singleton for direct imports/tests.
- [ ] **Cache hardening** (`cache.py`):
  - Raise TTL to a docs-appropriate value (target ~6–24h; configurable).
  - Bound size (LRU eviction) so it can't grow unbounded.
  - **Single-flight**: per-key `asyncio.Lock` so concurrent misses fetch once (no stampede).
  - Preserve existing `_cache`, `_cache_get`, `_cache_set` names/semantics OR update tests in lockstep.
- [ ] **Logging → stderr** (`server.py`): configure handler on stderr explicitly; never stdout (stdio MCP
  protocol corruption). Default level WARNING, env-overridable.
- [ ] **MCP tool annotations**: mark all 6 tools `readOnlyHint=True`, `openWorldHint=True`; pin stdio transport
  explicitly in `mcp.run()`.

## P1 — structural quality (the markdown pivot)

- [ ] **`markdown.py` — content acquisition**:
  - `resolve_md_url(path)`: implement `<path>.md` → `<path>/index.md` → `index.md` fallback.
  - `resolve_includes(md, base)`: parse `{* … *}` and legacy `{!…!}`; fetch referenced `docs_src/<...>.py`
    (parallel + cached); inline as fenced ```python blocks. Cap include count/size; on fetch failure, keep
    a readable placeholder rather than the raw directive.
  - `clean_mkdocs(md)`: strip `{ #anchor }` heading suffixes; reduce `<div class="termy">…</div>` console
    blocks to plain fenced ```console (drop font/span/`<u>` tags & escape codes); normalize `///` admonitions
    to markdown (e.g. `> **Note**`); collapse whitespace.
  - Keep `truncate_content` (paragraph-aware) — markdown headings give cleaner break points.
- [ ] **`content.py` — the fallback seam** (preserves "never breaks"):
  `fetch_content(path)` tries markdown (`markdown.py`); on unresolved md URL / failed include resolution /
  empty cleaned output, transparently falls back to live-site HTML (`html.py`). All tools call this, so any
  sitemap-discovered page is always served even if the GitHub repo reorganizes or include syntax changes again.
- [ ] **Rewire the 6 tools** (`tools.py`) onto `fetch_content`:
  - `get_fastapi_docs`, `search_fastapi_docs`, `get_fastapi_best_practices`: fetch via the chain, clean.
  - `get_fastapi_example`: prefer **resolved `docs_src` files** (pure runnable Python); fall back to
    HTML-scraped `<pre><code>` if markdown/include path is unavailable.
  - `compare_fastapi_approaches`: same content path; derive page titles from the leading `# H1`.
- [ ] **Slim, don't delete, the HTML extractor**: keep a lean `html.py` (drop the O(n²) stabilize loop;
  retain entity decode + tag strip + code-block extract) as the fallback. Net regex reduction without losing
  the resilience net. `_HTML_ENTITIES` etc. move here, not to the bin.
- [ ] **Make `compare_fastapi_approaches` self-healing + dynamic** (current `main.py:562-646`):
  - De-dup: canonical configs keyed by topic + separate `alias → canonical` map (removes verbatim repetition).
  - **Self-heal:** validate each curated page against the live sitemap at runtime; silently drop pages that no
    longer exist instead of emitting dead sections.
  - **Dynamic fallback:** for a topic NOT in the curated map, fall back to a sitemap search and compare the top
    sibling pages — so new/unknown comparison topics still work without a code change. Curation stays only where
    it adds judgment (e.g. "sync vs async"); everything else degrades dynamically.
- [ ] **Security hardening** (`http.py`):
  - Host **allowlist** (`fastapi.tiangolo.com`, `raw.githubusercontent.com`); validate the *final* URL host
    after redirects; reject otherwise.
  - **Streamed, byte-capped** download (cap before `.text`) to bound memory.
  - **Input validation** on tool args: max length, strip control chars, reject schemes/`..` traversal in `path`.

## P2 — maintainability polish

- [ ] **Test strategy**: mock network in unit tests (fixtures of canned md/sitemap); move the 2 live-network
  tests behind a `@pytest.mark.integration` marker (registered in pyproject, deselected by default in CI).
  Keep coverage gate ≥90%. Add tests for include-resolution, md-url fallback, single-flight, allowlist reject.
- [ ] **Remove `test_tools.py`** (root) — redundant manual script duplicating the suite.
- [ ] Update `README.md` Tools section if behavior/output shape changes (note GitHub-source provenance).
- [ ] Refresh `.github/copilot-instructions.md` / `CLAUDE.md` only if structure references drift.

---

## Risks & mitigations
- **Coupling to GitHub repo internals** (layout + include syntax, which has changed before) → **resolved by the
  markdown→HTML fallback seam**: any sitemap page is still served if the repo drifts. This is the explicit
  defense of the "never breaks on upstream change" principle. `master` is the default; optional pin to a
  release tag for reproducibility.
- **GitHub is a second upstream** (raw.githubusercontent) → covered by allowlist; longer cache TTL absorbs it.
- **Include resolution = extra fetches** → parallelized + cached + capped; section roots cost at most one extra
  probe. Net latency still far below today thanks to the shared client.
- **Behavior change in tool output** (markdown vs stripped text) → update assertions; this is the intended
  token-efficiency improvement, not a regression. HTML fallback keeps old-shape output available.
- **Curated `compare` map going stale** → runtime sitemap validation drops dead pages; dynamic search covers
  uncurated topics. No silent breakage when upstream renames pages.
- **Test churn** from renamed internals/module moves → update imports in `tests/test_main.py` in the same PR.
  Add tests: md→HTML fallback triggers correctly, compare self-heal drops a 404'd page, dynamic compare fallback.

## Verification gates (each step)
- `uv run ruff check . && uv run ruff format --check .`
- `uv run mypy main.py` (strict) — extend to the package path.
- `uv run bandit -c pyproject.toml --quiet -r src main.py`
- `uv run pytest --cov --cov-fail-under=90`
- Manual smoke: run each tool against a live path; confirm clean markdown + real Python examples + token size ↓.

## Suggested sequencing (small, reviewable PRs)
1. P0 (client + cache + logging + annotations) — no behavior change to content. ✅ ship first.
2. Package skeleton move (mechanical) + test import updates.
3. Markdown pivot (`markdown.py` + tool rewire) + compare-dict dedup + delete regex.
4. Security hardening + test-strategy overhaul + cleanup.

## Review (implementation complete)

**Shipped.** Single-file `main.py` → `fastapi_docs_mcp/` package (config, cache, http,
sitemap, markdown, html, content, tools, server) + thin `main.py` entrypoint shim.

Verification (all green):
- `ruff check` + `ruff format --check`: pass
- `mypy --strict` (main.py + package, 11 files): pass
- `bandit -r`: exit 0
- `pytest`: 68 passed, **97.6% coverage** (gate 90%); 2 live tests behind `-m integration`
- `uv build`: wheel bundles package + main.py; Dockerfile updated to copy the package

Token utilization (full data: [`bench/token-report.md`](../bench/token-report.md)):
**−8.2% overall** (7939 → 7289), 4/6 tools down-or-flat, `best_practices` −22.7%.
`search` is +13% — the documented "more-correct content" case (full CORSMiddleware
param reference the old scrape dropped).

Done across all goals:
- **Performance:** shared pooled loop-aware `httpx.AsyncClient`; 6h TTL + LRU +
  single-flight cache; parallel include/page fetches.
- **Token utilization:** markdown source; console→commands; image/link/schema trims. ✅ net win.
- **Security:** host allowlist (post-redirect), streamed byte cap, input sanitization,
  stderr logging.
- **Maintainability:** 9 focused modules; `compare` dedup + self-heal + dynamic fallback;
  fragile regex fence-splitter replaced by a robust line-state machine.
- **MCP best practices:** `readOnlyHint`/`openWorldHint` annotations; explicit stdio;
  client lifespan.
- **Resilience preserved:** sitemap-driven discovery unchanged; markdown→HTML fallback
  keeps every discoverable page reachable.

Follow-ups (optional, not blocking): consider pinning the GitHub source to a release
tag instead of `master` for reproducibility; README refresh to mention GitHub provenance.
