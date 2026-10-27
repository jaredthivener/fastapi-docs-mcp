"""Eval cases: realistic user questions graded on outcome (facts in the answer).

``facts`` is a list of any-of groups: every group must have at least one
alternative present (case-insensitive substring) in the final answer. Facts are
taken from the live FastAPI docs and each case's ``oracle`` call(s) must contain
them (checked by ``verify_oracle.py``) -- gold is never a model's output.
``tools_expected=False`` marks off-scope questions where calling a docs tool is
the wrong behaviour (both-directions coverage); they pass only with zero tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Case:
    """One eval question."""

    id: str
    tool: str  # server tool this case is designed to exercise ("-" if off-scope)
    question: str
    facts: tuple[tuple[str, ...], ...] = ()
    oracle: tuple[tuple[str, dict[str, str]], ...] = field(default=())
    tools_expected: bool = True


CASES: tuple[Case, ...] = (
    Case(
        "docs-first-steps",
        "get_fastapi_docs",
        "In the official FastAPI first-steps tutorial, which CLI command starts the development server?",
        (("fastapi dev",),),
        (("get_fastapi_docs", {"path": "tutorial/first-steps"}),),
    ),
    Case(
        "docs-websockets",
        "get_fastapi_docs",
        "In FastAPI's WebSockets docs, how is a WebSocket endpoint declared, and what must the server call before sending data?",
        (("@app.websocket",), ("accept()",)),
        (("get_fastapi_docs", {"path": "advanced/websockets"}),),
    ),
    Case(
        "docs-bigger-apps",
        "get_fastapi_docs",
        "In FastAPI's 'Bigger Applications - Multiple Files' guide, which class groups path operations into separate modules?",
        (("apirouter",),),
        (("get_fastapi_docs", {"path": "tutorial/bigger-applications"}),),
    ),
    Case(
        "search-cors",
        "search_fastapi_docs",
        "How do I enable CORS in a FastAPI app? Name the middleware class and the option that sets the allowed origins.",
        (("corsmiddleware",), ("allow_origins",)),
        (("search_fastapi_docs", {"query": "cors"}),),
    ),
    Case(
        "search-static",
        "search_fastapi_docs",
        "How do I serve static files from a FastAPI app?",
        (("staticfiles",), ("mount",)),
        (("get_fastapi_docs", {"path": "tutorial/static-files"}),),
    ),
    Case(
        "search-background",
        "search_fastapi_docs",
        "How do I run work after returning a response in FastAPI? Name the class and the method used to schedule it.",
        (("backgroundtasks",), ("add_task",)),
        (("get_fastapi_docs", {"path": "tutorial/background-tasks"}),),
    ),
    Case(
        "list-docker",
        "list_fastapi_pages",
        "Which page of the FastAPI docs covers deploying with Docker? Give its docs path.",
        (("deployment/docker",),),
        (("list_fastapi_pages", {}),),
    ),
    # list_fastapi_pages truncates each section ("... and 21 more"), so this page is
    # not reachable via the list; search is the oracle (see docs/EVAL.md finding).
    Case(
        "find-testing",
        "search_fastapi_docs",
        "What is the docs path of FastAPI's testing tutorial page?",
        (("tutorial/testing",),),
        (("search_fastapi_docs", {"query": "testing"}),),
    ),
    Case(
        "list-ws-testing",
        "list_fastapi_pages",
        "Does the FastAPI documentation have a page on testing WebSockets? Give its docs path.",
        (("advanced/testing-websockets",),),
        (("list_fastapi_pages", {}),),
    ),
    Case(
        "example-websocket",
        "get_fastapi_example",
        "Show me a minimal FastAPI WebSocket echo example in code.",
        (("websocket",), ("receive_text", "send_text")),
        (("get_fastapi_example", {"topic": "websockets"}),),
    ),
    Case(
        "example-jwt",
        "get_fastapi_example",
        "Give me example code for JWT authentication with FastAPI (creating and verifying tokens).",
        (("jwt",), ("oauth2passwordbearer",)),
        (("get_fastapi_example", {"topic": "jwt"}),),
    ),
    Case(
        "example-cors",
        "get_fastapi_example",
        "Code example: add CORS to a FastAPI app.",
        (("corsmiddleware",), ("add_middleware",)),
        (("get_fastapi_example", {"topic": "cors"}),),
    ),
    Case(
        "compare-sync-async",
        "compare_fastapi_approaches",
        "When should I use `async def` versus plain `def` for FastAPI path operation functions?",
        (("async def",), ("await",)),
        (("compare_fastapi_approaches", {"topic": "sync-async"}),),
    ),
    Case(
        "compare-auth",
        "compare_fastapi_approaches",
        "Compare the authentication approaches the FastAPI docs cover, such as OAuth2 with JWT versus HTTP Basic.",
        (("oauth2",), ("basic",)),
        (("compare_fastapi_approaches", {"topic": "auth-methods"}),),
    ),
    Case(
        "compare-deps",
        "compare_fastapi_approaches",
        "What dependency patterns does FastAPI support, and how do they differ?",
        (("depends",), ("class",)),
        (("compare_fastapi_approaches", {"topic": "dependency-patterns"}),),
    ),
    Case(
        "bp-security",
        "get_fastapi_best_practices",
        "What are the FastAPI security best practices I should follow?",
        (("oauth2",), ("password",)),
        (("get_fastapi_best_practices", {"topic": "security"}),),
    ),
    Case(
        "bp-testing",
        "get_fastapi_best_practices",
        "What are best practices for testing a FastAPI app?",
        (("testclient",),),
        (("get_fastapi_best_practices", {"topic": "testing"}),),
    ),
    Case(
        "bp-dependencies",
        "get_fastapi_best_practices",
        "What are best practices for using dependencies in FastAPI?",
        (("depends",), ("yield",)),
        (("get_fastapi_best_practices", {"topic": "dependencies"}),),
    ),
    Case(
        "offscope-django",
        "-",
        "What is the difference between Django REST framework serializers and Flask-RESTful request parsers?",
        tools_expected=False,
    ),
    Case("offscope-haiku", "-", "Write a haiku about autumn.", tools_expected=False),
)
