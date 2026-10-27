---
name: bench-tokens
description: Measure per-tool output token counts and compare against the committed baseline. Use after changing markdown.py, html.py, or any tool's response formatting, since this project's value is token efficiency.
disable-model-invocation: true
allowed-tools: Bash(uv run --with tiktoken python bench/benchmark.py *)
---

The benchmark hits the live network and uses tiktoken `cl100k_base` as a deterministic proxy (absolute numbers are approximate; the before/after comparison is apples-to-apples).

1. `uv run --with tiktoken python bench/benchmark.py after > "$TMPDIR/bench-after.json"`
2. Compare per-tool token counts to `bench/latest.json`.
3. Report a table: tool, baseline tokens, new tokens, delta %.
4. Flag any tool whose output grew. Do not overwrite `bench/latest.json` unless asked.
