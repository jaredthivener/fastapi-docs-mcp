# FastAPI Docs MCP Server — AI Agent Guide

## Project Overview
**FastAPI Docs MCP** is a Model Context Protocol server that provides real-time access to FastAPI documentation via tools. It fetches HTML from `fastapi.tiangolo.com`, parses content, and exposes 6 tools: `get_fastapi_docs`, `search_fastapi_docs`, `list_fastapi_pages`, `get_fastapi_example`, `compare_fastapi_approaches`, and `get_fastapi_best_practices`.

The entire application is a single-file async tool server (`main.py`). Focus is on robust HTML parsing and sitemap-driven content discovery.

## Key Architecture Patterns

### HTML Parsing Without External Dependencies
- **No BeautifulSoup**: Uses `re.sub()` with regex patterns to extract text and code blocks. This is intentional to minimize dependencies.
- **Extraction pipeline** (in `extract_text_from_html()`):
  1. Remove non-content elements: `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`
  2. Extract `<article>` tag content (prioritized)
  3. Iteratively strip remaining HTML tags until stable
  4. Decode HTML entities AFTER tag removal (critical ordering)
  5. Clean up malformed HTML artifacts
- **Code extraction** (in `extract_code_blocks()`): Finds `<pre><code>` blocks first, then fallback to multi-line `<code>` blocks. Always removes tags before decoding entities.

### Sitemap-Driven Discovery
- `fetch_sitemap()` parses `fastapi.tiangolo.com/sitemap.xml` to get all doc URLs
- `categorize_urls()` maps paths to: `tutorial`, `advanced`, `deployment`, `how-to`, `reference`, `other`
- Multiple tools (`search_fastapi_docs`, `get_fastapi_best_practices`) dynamically query this list—**no hardcoded doc paths** except in `get_fastapi_example()` and `compare_fastapi_approaches()` for performance

### Keyword Aliasing
- `search_fastapi_docs()` includes alias mappings: `auth→security`, `db→sql-databases`, `di→dependencies`, etc.
- `get_fastapi_example()` and `compare_fastapi_approaches()` have pre-computed `topic_paths` dicts for direct lookups
- Fallback: if no alias matches, search the sitemap directly

### Content Truncation
- Tools return truncated content (`MAX_CONTENT_LENGTH = 15_000`) with `... [Content truncated]` indicator
- `truncate_content()` prefers paragraph breaks (`\n\n`) over mid-word cuts for readability

## Development & Testing

### Testing Approach
- **Integration tests** (`tests/test_main.py`): Test real HTTP calls to `fastapi.tiangolo.com` (uses `pytest-asyncio`)
- **Quick validation** (`test_tools.py`): Manual script testing all 6 tools end-to-end
- **Run tests**: `uv run pytest` (Python 3.13/3.14 only)

### Code Quality (Enforced by CI/CD)
- **Ruff**: `uv run ruff check .` (linting) + `uv run ruff format .` (formatting)
- **Type checking**: `uv run mypy main.py` (strict typing required)
- **Security**: `uv run bandit main.py` (no external SSTI exploits)
- **Config**: Set target Python 3.13+ in `pyproject.toml` — do NOT add Python 3.12 support

## Contributing Guidelines
- All functions must have **full type hints** and **docstrings** (checked by mypy)
- New tools must be decorated with `@mcp.tool` and return `str`
- Test coverage is expected for new logic (see `tests/test_main.py` structure)
- PR checklist: Run all checks locally before pushing (CONTRIBUTING.md)

## Common Tasks

### Adding a New Tool
1. Create async function with `@mcp.tool` decorator, `str` return type
2. Use `fetch_url()` for HTTP calls (includes timeout, redirect handling)
3. Use `extract_text_from_html()` or `extract_code_blocks()` for parsing
4. Return formatted markdown with URL reference
5. Add tests in `tests/test_main.py`

### Fixing HTML Parsing Issues
- Test HTML extraction locally: use `extract_text_from_html(html)` in REPL
- Common problem: entity decoding order. **Always decode after removing tags**, not before
- If regex fails, add a specific case to `extract_text_from_html()` for that element type

### Debugging HTTP Failures
- `fetch_url()` returns `None` on any `httpx.HTTPError`. Check timeout (30s) and URL format
- Tools have fallback logic (e.g., `get_fastapi_docs` tries both with/without trailing slash)
- Sitemap fetch failures gracefully return empty list — tools then suggest `list_fastapi_pages()`

## Codebase Conventions
- Async-first: All tools are `async def`, network calls use `async with httpx.AsyncClient()`
- Constants at module top: `BASE_URL`, `SITEMAP_URL`, `REQUEST_TIMEOUT`, `MAX_CONTENT_LENGTH`
- Error messages are user-friendly (suggest `list_fastapi_pages()` or browse docs)
- Tools always return non-None string (no exceptions; failures are graceful)

## Performance Notes
- Sitemap is fetched fresh per tool call (not cached) — acceptable for interactive use, revisit if latency becomes issue
- Code extraction limits results to first 5 examples to avoid token bloat
- Best practices tool limits to first 3 pages (most relevant) to manage response size
