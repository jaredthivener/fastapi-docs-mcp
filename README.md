<h1 align="center">🐍 FastAPI Docs MCP Server 🤖</h1>

<p align="center">
    <em>Real-time FastAPI documentation access for AI assistants</em>
</p>
<p align="center">
<a href="https://github.com/jaredthivener/fastapi-docs-mcp/actions/workflows/test.yml" target="_blank"><img src="https://github.com/jaredthivener/fastapi-docs-mcp/actions/workflows/test.yml/badge.svg?event=push&branch=main" alt="Test"></a>
<a href="https://github.com/jaredthivener/fastapi-docs-mcp/actions/workflows/codeql.yml" target="_blank"><img src="https://github.com/jaredthivener/fastapi-docs-mcp/actions/workflows/codeql.yml/badge.svg" alt="CodeQL"></a>
<a href="https://github.com/jaredthivener/fastapi-docs-mcp/blob/main/LICENSE" target="_blank"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
<a href="https://github.com/jaredthivener/fastapi-docs-mcp" target="_blank"><img src="https://img.shields.io/badge/python-3.13%2B-blue.svg" alt="Python 3.13+"></a>
</p>

---

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that provides real-time access to [FastAPI](https://fastapi.tiangolo.com/) documentation. Use it with Claude, GitHub Copilot, or any MCP-compatible client to instantly query FastAPI docs.

## Features

- **Real-time documentation** — Fetches directly from fastapi.tiangolo.com
- **Smart search** — Find docs by keyword with common alias support
- **Full sitemap access** — Browse all available documentation pages
- **Code examples** — Get just the code, no prose
- **Compare approaches** — Side-by-side comparisons of different patterns

## Tools

| Tool | Description |
|------|-------------|
| `get_fastapi_docs(path)` | Fetch any documentation page by path |
| `search_fastapi_docs(query)` | Search docs by keyword (with alias support) |
| `list_fastapi_pages()` | List all available documentation pages |
| `get_fastapi_example(topic)` | Get just the code examples, no prose |
| `compare_fastapi_approaches(topic)` | Compare different approaches side-by-side |

## Installation

```bash
git clone https://github.com/jaredthivener/fastapi-docs-mcp.git
cd fastapi-docs-mcp
uv sync
```

## Usage

### With Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "fastapi-docs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/fastapi-docs-mcp", "python", "main.py"]
    }
  }
}
```

### With VS Code (GitHub Copilot)

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "fastapi-docs": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/fastapi-docs-mcp", "python", "main.py"]
    }
  }
}
```

### With Docker

Build the image locally:

```bash
docker build -t fastapi-docs-mcp .
```

Then use this MCP server config:

```json
{
  "servers": {
    "fastapi-docs": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "fastapi-docs-mcp"
      ],
      "type": "stdio"
    }
  }
}
```

### Standalone

```bash
uv run python main.py
```

## Examples

Once connected, ask your AI assistant:

- "How do I set up CORS in FastAPI?"
- "Show me the FastAPI security documentation"
- "What are FastAPI dependencies?"
- "List all FastAPI tutorial pages"
- "Give me a code example for JWT authentication"
- "Compare sync vs async in FastAPI"

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy main.py
```

## How It Works

The server fetches documentation directly from the official FastAPI website:

1. **Sitemap-based discovery** — Uses `sitemap.xml` to find all available pages
2. **Real-time fetching** — Retrieves current documentation on each request
3. **Smart extraction** — Extracts readable content from HTML pages
4. **Keyword aliases** — Maps common terms (e.g., "auth" → "security")

## Content Limits

To keep responses fast and avoid overloading AI context windows, documentation content is truncated to a maximum length (currently **15,000 characters**). If a page exceeds that limit, the response ends with a truncation notice and a link to the full page.

## License

MIT
