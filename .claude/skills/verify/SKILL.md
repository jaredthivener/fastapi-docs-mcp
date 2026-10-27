---
name: verify
description: Run the exact CI gate locally (ruff lint, ruff format check, mypy strict, pytest with 95% coverage). Use before claiming any code change is done or before opening a PR.
allowed-tools: Bash(uv run ruff *) Bash(uv run mypy *) Bash(uv run pytest *) Bash(uv sync *)
---

Run the same commands as `.github/workflows/test.yml`, in this order, and stop at the first failure:

1. `uv sync --locked --extra dev`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run mypy src/fastapi_docs_mcp --ignore-missing-imports`
5. `uv run pytest --cov=fastapi_docs_mcp --cov-report=term-missing --cov-fail-under=95`

Report each step as pass/fail with the failing output verbatim. Do not claim "done" unless all five pass.
Live-network tests (`-m integration`) are opt-in and not part of this gate.
