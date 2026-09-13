# Contributing to FastAPI Docs MCP

Thank you for your interest in contributing! 🎉

## Requirements

Before your PR can be merged, it must pass all automated checks:

- ✅ **Linting** — `uv run ruff check .` (includes security linting via ruff's `S` rules)
- ✅ **Formatting** — `uv run ruff format --check .`
- ✅ **Type checking** — `uv run mypy src/fastapi_docs_mcp`
- ✅ **Tests** — `uv run pytest` (Python 3.13 and 3.14)
- ✅ **Security** — CodeQL analysis

## Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/fastapi-docs-mcp.git
cd fastapi-docs-mcp

# Install dependencies (requires uv)
uv sync --extra dev

# Run all checks locally before pushing
uv run ruff check .
uv run ruff format .
uv run mypy src/fastapi_docs_mcp --ignore-missing-imports
uv run pytest
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run all checks locally (see above)
5. Commit with a descriptive message
6. Push to your fork
7. Open a PR against `main`

## Code Style

- Python 3.13+ only
- Follow existing code patterns
- Add type hints to all functions
- Include docstrings for public functions
- Keep functions focused and small

## Questions?

Open an issue if you have questions or need help!
