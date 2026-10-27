# Project: fastapi-docs-mcp

Python 3.15 FastMCP server exposing 6 read-only FastAPI-docs tools. Token efficiency is the product.

- Architecture, module map, and invariants: `.github/copilot-instructions.md` (read on demand, not imported)
- Tool contract: `AGENTS.md`; design rationale: `docs/DESIGN.md`
- Gate before "done" (mirrors CI): run the `/verify` skill. Edited `.py` files are auto-formatted and linted by a PostToolUse hook.
- New tool: `/add-mcp-tool`. After touching markdown/html/response formatting: `/bench-tokens`.
- Model eval (latency/accuracy/cost; uses your Claude plan's quota): `uv run python bench/model_eval.py`. Results: `docs/DESIGN.md` §7.
- Never edit `uv.lock` by hand (use `uv lock`/`uv add`); denied in `.claude/settings.json`.
- Invariants: tools call `content.py`/`sitemap.py`, never `http.py`; confirmed-absent (`None`) vs unreachable (`ToolError`) must stay distinct; every URL/limit lives in `config.py`; no new HTML-parsing dependency.
- Ground claims in evidence: cite the command output or file:line that proves a change works.

# Workflow Orchestration

## 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

## 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

## 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

## 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

## 5. Demand Elegance (Balanced)
- For non-trivial changes, pause and ask "is there a more elegant way?"
- If a fix feels hack: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

## 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Principal developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
