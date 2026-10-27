"""Outcome grader: facts present in the answer; off-scope cases need zero tool calls."""

from __future__ import annotations

from .cases import Case


def grade(case: Case, answer: str, n_tool_calls: int) -> bool:
    """Return True if ``answer`` satisfies ``case`` (any route to the facts counts)."""
    if not case.tools_expected:
        return n_tool_calls == 0 and bool(answer.strip())
    text = answer.lower()
    return bool(case.facts) and all(
        any(alt in text for alt in group) for group in case.facts
    )
