# FastAPI Docs MCP Server — AI Agent Guide

## Project Overview
**FastAPI Docs MCP** is a Model Context Protocol server providing real-time
access to FastAPI documentation. It exposes 6 read-only tools:
`get_fastapi_docs`, `search_fastapi_docs`, `list_fastapi_pages`,
`get_fastapi_example`, `compare_fastapi_approaches`, and
`get_fastapi_best_practices` — see [AGENTS.md](../AGENTS.md) for the full
tool contract (signatures, return shape, error semantics).

The implementation is a small package under `src/fastapi_docs_mcp/`, not a
single file. Each module is one layer:

| Module | Responsibility |
|---|---|
| `config.py` | Every magic value (URLs, allowlist, timeouts, limits) in one place |
| `http.py` | The single network choke point: host allowlist (enforced post-redirect), size cap, timeout |
| `cache.py` | TTL + LRU cache with single-flight de-duplication |
| `sitemap.py` | Discovery — the sitemap is the only source of page-path truth, plus keyword aliases |
| `markdown.py` | Preferred content path: raw GitHub markdown, include-directive resolution, MkDocs-syntax cleanup |
| `html.py` | Fallback-only content path: regex text/code extraction from the rendered site |
| `content.py` | Orchestrates markdown-then-HTML fallback; the one place that distinguishes a confirmed-absent page (`None`) from an unreachable one (`ToolError`) |
| `app.py` | The shared `FastMCP` instance, tool annotations, lifespan (closes the HTTP client) |
| `server.py` | Logging setup, imports `tools` to register it, `run()` |
| `tools.py` | The 6 `@mcp.tool` functions — thin orchestration + response formatting |

## Key Architecture Patterns

### Markdown-preferred, HTML-fallback content
`content.py` fetches FastAPI's raw markdown from GitHub first (token-efficient,
preserves code fences) and only falls back to parsing the rendered HTML page
if markdown is unavailable. This is the resilience guarantee: an upstream
change to one source degrades gracefully instead of breaking the tool.

### No HTML parsing library
`html.py` uses `re.sub()` regex passes rather than BeautifulSoup/lxml — it is
the fallback path only (exercised when markdown fails), kept deliberately
lean and covered by hypothesis property tests (`tests/test_html.py`).

### Sitemap-driven discovery
`sitemap.fetch_sitemap()` parses the live `sitemap.xml`; nothing hardcodes a
page inventory, so new/renamed upstream docs are found automatically.
`KEYWORD_ALIASES` maps user vocabulary (e.g. `auth` → `security`) to terms
that appear in sitemap URLs.

### Single-flight cache
Concurrent fetches for the same URL collapse into one upstream request
(`cache.get_or_fetch`). Entries expire after `CACHE_TTL` and the cache is
bounded by `CACHE_MAX_ENTRIES` (LRU-evicted).

### Confirmed-absent vs. unreachable
A page that genuinely doesn't exist returns `None` (handled softly, e.g. "no
results for X"). A page that couldn't be checked at all (every source failed
transiently) raises `fastmcp.exceptions.ToolError`. Collapsing these into one
"not found" response would misinform the caller — don't do it when touching
`content.py`, `http.py`, or `markdown.py`.

## Development & Testing

- **Unit tests** (`tests/`): network fully mocked, run by default — `uv run pytest`
- **Live tests** (`tests/test_live.py`): hit the real network, opt-in only —
  `uv run pytest -m integration` (also run on a schedule via `canary.yml`)
- **Property tests**: `tests/test_html.py` / `tests/test_markdown.py` use
  `hypothesis` to fuzz the regex extraction/cleanup pipelines

### Code Quality (enforced by CI)
- **Ruff**: `uv run ruff check .` (includes pep8-naming, pydocstyle/PEP 257,
  and flake8-bandit's `S` rules — there is no separate bandit dependency)
  + `uv run ruff format --check .`
- **Type checking**: `uv run mypy src/fastapi_docs_mcp` (`strict = true`)
- **Coverage gate**: `--cov-fail-under=95`
- Target Python 3.13+ — do not add 3.12 support

## Contributing Guidelines
- All functions have full type hints and docstrings (mypy strict + ruff `D`)
- New tools are decorated with `@mcp.tool(annotations=READONLY, ...)` in `tools.py`
- Add tests alongside the module you change (`tests/test_<module>.py`)
- PR checklist: see [CONTRIBUTING.md](../CONTRIBUTING.md)

## Common Tasks

### Adding a New Tool
1. Add an `async def` in `tools.py` decorated with `@mcp.tool(annotations=READONLY, output_schema=None)`
2. Call into `content.py`/`sitemap.py` — never `http.py` directly from a tool
3. Format the response as markdown with a source URL
4. Add tests in `tests/test_tools.py`

### Fixing HTML/Markdown Parsing Issues
- `html.py` and `markdown.py` each have hypothesis-based fuzz tests — run
  them (`uv run pytest tests/test_html.py tests/test_markdown.py`) after
  any regex change
- In `markdown.py`, HTML entities must be decoded *after* tags are stripped

### Debugging Fetch Failures
- `http.fetch()` returns `None` for a confirmed-absent/disallowed resource,
  raises `http.UpstreamError` if the fetch couldn't be completed at all
- `content.py`'s two-source fallback and `_fetch_live_html`'s two-URL-form
  retry (with/without trailing slash) already cover most transient failures
