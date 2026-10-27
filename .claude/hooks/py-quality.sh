#!/bin/bash
# PostToolUse hook (Edit|Write): keep Python edits CI-clean as they happen.
# Formats the edited file, then lints it. Lint findings go to stderr with exit 2
# so Claude sees and fixes them now, not after a failed CI run. Silent on success
# (no token cost). Non-Python files are ignored.
set -u
f=$(jq -r '.tool_input.file_path // empty')
case "$f" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$f" ] || exit 0

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
# ruff lives in the `dev` extra; --extra makes `uv run` provide it.
ruff() { uv run --quiet --extra dev ruff "$@"; }
ruff format --quiet "$f" >/dev/null 2>&1
out=$(ruff check --output-format=concise "$f" 2>&1)
# ruff exits 1 only when it found violations; any other failure (tool missing,
# offline) must not block the edit with a misleading "lint error".
if [ $? -eq 1 ]; then
  printf '%s\n' "$out" >&2
  exit 2
fi
