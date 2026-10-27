---
name: add-mcp-tool
description: Add a new read-only MCP tool to this server following the project's layering and test conventions. Use when asked to add, expose, or create a new tool.
argument-hint: [tool-name]
disable-model-invocation: true
---

Add the tool `$ARGUMENTS` to `src/fastapi_docs_mcp/tools.py`.

1. Read an existing tool in `tools.py` and mirror it (decorator, docstring, response shape).
2. `async def` decorated `@mcp.tool(annotations=READONLY, output_schema=None)`. Tools stay thin orchestration + markdown formatting.
3. Fetch only via `content.py` / `sitemap.py`. Never call `http.py` from a tool.
4. Response is markdown and includes the source URL.
5. Distinguish absent from unreachable: a confirmed-missing page is soft ("no results"); an unreachable one raises `ToolError`. Never collapse the two.
6. Any new constant (URL, limit, timeout) goes in `config.py`, not inline.
7. Add tests in `tests/test_tools.py` with the network mocked.
8. Update the tool tables in `AGENTS.md` and `.github/copilot-instructions.md`, and add a `CHANGELOG.md` entry under `[Unreleased]`.
9. Finish with the `/verify` skill.
