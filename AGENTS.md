# AGENTS.md — FastAPI Docs MCP Server

Agent configuration reference for clients connecting to this MCP server.

---

## Server identity

| Property | Value |
|---|---|
| Server name | `FastAPI-Docs-Expert` |
| Protocol | MCP over stdio (transport: `stdio`) |
| Runtime | FastMCP ≥ 3.4.2 |
| Entrypoint | `python main.py` |

---

## Tools

All six tools are **read-only** (`readOnlyHint: true`, `openWorldHint: true`).
None write files, mutate state, or execute code on the host.

### `get_fastapi_docs(path: str) → str`
Fetch the full content of a single FastAPI doc page by its path slug.

- **When to use**: the user names a specific topic, tutorial, or advanced page.
- **Input**: path slug, e.g. `"tutorial/first-steps"`, `"advanced/websockets"` (no leading slash, no trailing slash).
- **Output**: cleaned markdown with prose, Python code blocks, and the canonical URL.
- **Token cost** (tiktoken est.): ~2,490 output tokens for a typical page.

### `search_fastapi_docs(query: str) → str`
Keyword search across all sitemap URLs; returns the best-matching page's content plus up to 4 related paths.

- **When to use**: the user asks about a topic without naming an exact page; always try this before `get_fastapi_docs`.
- **Input**: plain search term, e.g. `"cors"`, `"database"`, `"websocket"`. Aliases like `"auth"` are resolved server-side.
- **Output**: best-match page content + related-page list.
- **Token cost** (tiktoken est.): ~1,221 output tokens.

### `list_fastapi_pages() → str`
List every page in the FastAPI sitemap, categorized by section (Tutorial, Advanced, Deployment, How-To, Reference).

- **When to use**: the user wants to browse, or when `search_fastapi_docs` returns no results.
- **Input**: none.
- **Output**: section-grouped bullet list with total page count.
- **Token cost** (tiktoken est.): ~844 output tokens.

### `get_fastapi_example(topic: str) → str`
Return Python code blocks only (no prose) for a topic — up to 5 examples from the best-matching page.

- **When to use**: the user explicitly asks for code or an example, not an explanation.
- **Input**: topic slug, e.g. `"cors"`, `"jwt"`, `"websockets"`.
- **Output**: fenced `python` blocks, source URL, example count.
- **Token cost** (tiktoken est.): ~147 output tokens.

### `compare_fastapi_approaches(topic: str) → str`
Side-by-side comparison of multiple FastAPI approaches (curated presets or dynamic multi-page synthesis).

- **When to use**: the user asks "which is better", "what's the difference", or "how do I choose".
- **Input**: comparison key, e.g. `"sync-async"`, `"auth-methods"`, `"dependency-patterns"`, `"response-types"`, `"testing"`, `"database"`. Aliases (`"auth"`, `"async"`, `"dependencies"`, `"response"`) are resolved. Any other topic triggers dynamic page matching.
- **Output**: per-approach heading, first code example (capped to 18 lines), one-sentence summary, docs URL.
- **Token cost** (tiktoken est.): ~459 output tokens.

### `get_fastapi_best_practices(topic: str) → str`
Combine content from up to 3 matching doc pages (Tutorial → Advanced → How-To → Reference priority), with a list of additional matching pages.

- **When to use**: the user asks for best practices, production guidance, or a synthesis across multiple pages.
- **Input**: topic keyword, e.g. `"security"`, `"testing"`, `"dependencies"`.
- **Output**: multi-section markdown (heading, URL, full page content per match, more-pages list).
- **Token cost** (tiktoken est.): ~2,128 output tokens.

---

## Tool call sequence

```
User question
  └── search_fastapi_docs(query)          ← always start here
        ├── found → read the returned page; done for most questions
        ├── need code only → get_fastapi_example(topic)
        ├── need full page → get_fastapi_docs(path)
        ├── need comparison → compare_fastapi_approaches(topic)
        ├── need synthesis → get_fastapi_best_practices(topic)
        └── no results → list_fastapi_pages() → pick a path → get_fastapi_docs(path)
```

Never answer a FastAPI question from model memory alone. If every tool returns empty or an error, say so explicitly and do not substitute a guessed answer.

---

## Model selection

Use the cheapest model that can handle the task. These tools are read-and-relay by nature; reserve expensive reasoning capacity for the surrounding task, not the lookup.

| Task type | Recommended model | Model ID |
|---|---|---|
| Single doc fetch, search, list, example | **Haiku 4.5** | `claude-haiku-4-5` |
| Multi-page synthesis (`best_practices`, `compare`) | **Sonnet 4.6** | `claude-sonnet-4-6` |
| Already inside a complex coding/agent Opus session | **Opus 4.8** | `claude-opus-4-8` |

**Precedence rule**: if the surrounding session already runs on Opus, stay on Opus — switching mid-session breaks the prompt cache and costs more than the downgrade saves. Otherwise, start at Haiku and step up only if the synthesis task requires it.

**Conflict rule**: when in doubt, prioritize verified tool output over model memory, then correctness over brevity.

---

## Permissions

The server makes outbound HTTPS GET requests only. No writes, no shell, no host filesystem access.

| Resource | Allowed |
|---|---|
| `https://fastapi.tiangolo.com/*` | ✅ |
| `https://raw.githubusercontent.com/fastapi/fastapi/*` | ✅ |
| Any other host | ❌ (SSRF allowlist enforced after redirects) |
| Host filesystem | ❌ |
| Shell / code execution | ❌ |
| Network writes (POST/PUT/DELETE) | ❌ |

---

## Caching

The server maintains an in-process TTL + LRU cache. Agents do not need to manage it, but it affects latency and upstream calls.

| Parameter | Value |
|---|---|
| TTL | 6 hours |
| Max entries | 256 |
| Eviction policy | LRU |
| Single-flight | yes — concurrent identical fetches coalesce |
| Cache scope | per server process (not shared across restarts) |

A cold first call to `get_fastapi_docs` fetches live markdown from GitHub (~30 s timeout, 5 MB body cap). Subsequent calls to the same path within 6 hours return instantly from cache.

---

## Token budget

Tool definitions add a fixed overhead on every request:

| Payload | Tokens (tiktoken) | Claude-adjusted (×1.2) |
|---|---:|---:|
| All 6 tool definitions (full wire payload) | 554 | ~665 |

Tool outputs (per-call variable cost):

| Tool | tiktoken | Claude-adj. |
|---|---:|---:|
| `get_fastapi_example` | 147 | ~176 |
| `compare_fastapi_approaches` | 459 | ~551 |
| `list_fastapi_pages` | 844 | ~1,013 |
| `search_fastapi_docs` | 1,221 | ~1,465 |
| `get_fastapi_best_practices` | 2,128 | ~2,554 |
| `get_fastapi_docs` | 2,490 | ~2,988 |

**Prompt caching**: the tool-definition block is byte-stable (never mutated per request), making it a clean cacheable prefix. Enable prompt caching to pay only ~0.1× on repeated sessions.

---

## Input validation

The server sanitizes all arguments before use. Agents do not need to pre-sanitize, but should avoid inputs that trigger these limits:

| Constraint | Value |
|---|---|
| Max argument length | 256 characters |
| Control characters | stripped |
| Path traversal sequences | stripped (`..`, `.`, leading `/`) |
| Markdown include directives resolved per page | max 16 |

---

## Guardrails

- Never present a FastAPI answer that the tool output did not confirm.
- If the retrieved docs are version-ambiguous or truncated, say so and offer to fetch the exact page.
- For security and deployment topics, add explicit caveats; do not present unverified advice as official guidance.
- If the user asks about non-FastAPI topics, say the server is scoped to FastAPI documentation and ask whether to continue within that scope.
- If a tool call fails or returns no relevant results, report the failure rather than answering from memory.
- If tools return conflicting information for the same topic, prefer the most specific retrieved page, state the conflict, and do not merge unsupported details.
