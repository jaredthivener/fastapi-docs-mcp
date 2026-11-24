---
name: mutation-test
description: Run mutmut on content.py and sitemap.py to find code that tests execute but never assert on (coverage alone can't). Use after changing either module or its tests, or when auditing test quality. Opt-in; not part of the CI gate.
disable-model-invocation: true
allowed-tools: Bash(uv run --with mutmut mutmut *) Bash(rm -rf mutants)
---

mutmut mutates the code (flips operators, swaps `and`/`or`, drops arguments, nulls values) and re-runs the tests. A **surviving** mutant means the line ran but nothing would fail if it were wrong. mutmut is deliberately **not** a dependency: `--with` keeps `pyproject.toml` deps and `uv.lock` untouched. Scope and test selection live in `[tool.mutmut]` in `pyproject.toml` (~3 s for ~173 mutants).

1. `rm -rf mutants` (a stale run hides new mutants)
2. `uv run --with mutmut mutmut run`
3. `uv run --with mutmut mutmut results --all true | sed 's/.*: //' | sort | uniq -c` for the killed/survived totals.
4. For each survivor from `uv run --with mutmut mutmut results | grep survived`, read it with `uv run --with mutmut mutmut show <name>` and classify:
   - **Real gap** → write a test that fails on the mutant (assert the observable outcome: URLs requested, message text, ordering, the `None` vs `ToolError` split), re-run, confirm it is killed.
   - **Equivalent** (no behavior change) → leave it; do not write a contrived test. Prove it: run original and mutant over many inputs and show zero divergence, don't just assert it.
5. Report `killed/total`, and each survivor as real-gap (now killed) or equivalent (with the evidence). Cite command output.

## Known equivalent survivors (baseline: 165/173 killed, 8 survived)

mutant names are index-based and shift when the code changes; match on the diff.

- `strip("/")` → `strip("XX/XX")` (3×: `_fetch_live_html`, `search_sitemap_urls`, `categorize_urls`): strips the *character set* {X, /}; identical for lowercase slugs.
- `had_error = False` → `None` in `_fetch_live_html`: only ever tested for truthiness.
- `category != "other"` → `"XXotherXX"`/`"OTHER"` in `categorize_urls` (2×): the guard is redundant because `other` is the `for/else` fallback bucket.
- `KEYWORD_ALIASES.get(slug)` → `.get(None)` in `match_paths`: the single-word recursion yields the same result (0 divergences over 3,008 queries).
- `UpstreamError(f"...")` → `UpstreamError(None)` in `_fetch_live_html`: message only; both callers swallow it.

A survivor **not** in this list is new: treat it as a real gap until proven otherwise.
If you change `content.py`/`sitemap.py` or their tests, re-run and update this list and the baseline in the same PR, or it rots.

## Gotchas

- Hypothesis suites (`test_html.py`, `test_markdown.py`) are excluded from the selection: mutmut reuses one process, which fails Hypothesis's `differing_executors` health check. Don't add them without `suppress_health_check`.
- `also_copy = ["src/"]` is required: mutmut copies only the mutated files, so sibling modules would be missing.
- To widen scope, add files to `source_paths`. For `markdown.py`/`html.py`, select only the example-based classes in `pytest_add_cli_args_test_selection` (`tests/test_markdown.py::TestMarkdown`, `tests/test_html.py::TestHtml`) so the Hypothesis classes stay out. Run that wider scope in a scratch copy first: it has ~70 pre-existing survivors (e.g. `_render_code_block`, `extract_text`) that are not triaged.
- Output goes to `mutants/` (gitignored). Never commit it.
