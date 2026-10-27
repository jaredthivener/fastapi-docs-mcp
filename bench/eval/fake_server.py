"""Local fake of the Messages streaming API for ``--dry-run`` (no cost, no network).

For a known eval question it first emits a ``tool_use`` for the case's oracle tool,
then (after the tool_result) a text answer containing every required fact, so the
whole loop -- SDK stream parsing, MCP tool calls, grading, accounting -- is
exercised end to end. Off-scope cases get a plain text answer.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .cases import CASES

_BY_QUESTION = {c.question: c for c in CASES}


def _sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(
        f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
    ).encode()


def _message(
    model: str, blocks: list[dict[str, Any]], stop: str
) -> list[dict[str, Any]]:
    usage = {"input_tokens": 900, "output_tokens": 1}
    ev: list[dict[str, Any]] = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_fake",
                "type": "message",
                "role": "assistant",
                "model": model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": usage,
            },
        }
    ]  # fmt: skip
    for i, b in enumerate(blocks):
        start = {**b, "text": ""} if b["type"] == "text" else {**b, "input": {}}
        ev.append({"type": "content_block_start", "index": i, "content_block": start})
        delta = (
            {"type": "text_delta", "text": b["text"]}
            if b["type"] == "text"
            else {"type": "input_json_delta", "partial_json": json.dumps(b["input"])}
        )
        ev.append({"type": "content_block_delta", "index": i, "delta": delta})
        ev.append({"type": "content_block_stop", "index": i})
    ev.append(
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop, "stop_sequence": None},
            "usage": {"output_tokens": 40},
        }
    )
    ev.append({"type": "message_stop"})
    return ev


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        first = body["messages"][0]["content"]
        case = _BY_QUESTION[first if isinstance(first, str) else first[0]["text"]]
        has_result = body["messages"][-1]["role"] == "user" and isinstance(
            body["messages"][-1]["content"], list
        )
        if body.get("tools") and case.tools_expected and not has_result:
            name, args = case.oracle[0]
            blocks = [
                {"type": "tool_use", "id": "toolu_fake", "name": name, "input": args}
            ]
            events = _message(body["model"], blocks, "tool_use")
        else:
            facts = " ".join(g[0] for g in case.facts) or "Out of scope."
            events = _message(
                body["model"], [{"type": "text", "text": facts}], "end_turn"
            )
        payload = _sse(events)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: object) -> None:
        """Silence request logging."""


def start() -> tuple[ThreadingHTTPServer, str]:
    """Start the fake API on a free localhost port; return (server, base_url)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
