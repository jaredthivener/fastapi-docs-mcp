# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

History before this file was added is not backfilled — no git tags or
GitHub releases exist to anchor version boundaries accurately, and guessing
at them from commit messages would not be verifiable.

## [Unreleased]

### Fixed
- Single-flight cache (`cache.py`) leaked one `asyncio.Lock` per key that was
  fetched but never cached (e.g. a confirmed-404 path) — locks were only
  reaped on cache eviction/expiry, never on the fetch they guarded settling.
  Now reaped immediately regardless of outcome.
- `mcp-types` is now a declared direct dependency (was only present
  transitively via `fastmcp`) — `server.py`/`app.py` import it directly.
- `fastmcp` lower bound corrected to `>=4.0.3` (the code has required 4.x
  APIs since the `fastmcp.server`/`mcp_types` import move).
- CI now runs `uv sync --locked`, and the Docker builder stage now copies
  `uv.lock` and runs `uv sync --locked --no-dev` — both previously could
  resolve outside the committed lockfile.
- `USER_AGENT` now reads the installed package version via
  `importlib.metadata` instead of a hardcoded, already-stale `"2.0"`.

### Changed
- Replaced the standalone `bandit` dependency/CI step with ruff's `S`
  (flake8-bandit) ruleset — verified equivalent (zero findings either way)
  on this codebase.
- Enabled ruff's `N` (pep8-naming), `D` (pydocstyle/PEP 257), `RUF`,
  `ASYNC`, `PLE`/`PLW`, `TID`, and `DTZ` rulesets, and removed the `E501`
  ignore, for full PEP 8 enforcement.
- Replaced the hand-rolled 9-entry HTML entity table with stdlib
  `html.unescape` (full HTML5 entity coverage), keeping the deliberate
  `&para;`/`&sect;` anchor-glyph stripping as an explicit post-decode step.
- `compare_fastapi_approaches` and `get_fastapi_best_practices` now fetch
  their (independent) per-page content concurrently via `asyncio.gather`
  instead of one page at a time.
- Split the single 30s request timeout into per-phase
  `httpx.Timeout(connect=5, read=15, write=5, pool=5)`.
- Ratcheted the CI coverage gate from 90% to 95% (measured coverage is
  ~98%; 90% permitted a large silent regression).
- Pinned every third-party GitHub Action (across all workflows) to a
  commit SHA instead of a floating version tag; added the missing
  top-level `permissions:` block to `test.yml`/`canary.yml`; added a CI
  job that builds the Dockerfile so it can no longer drift silently.
- Removed the circular-import workaround in `server.py` (importing `tools`
  at the bottom of the file behind `# noqa: E402`) by splitting the shared
  `FastMCP` instance into its own `app.py` module that both `server.py` and
  `tools.py` import independently.

### Removed
- `main.py` entrypoint shim, replaced by a proper
  `[project.scripts] fastapi-docs-mcp` console-script entrypoint. The
  Dockerfile, `.vscode/mcp.json`, and README are updated accordingly.
