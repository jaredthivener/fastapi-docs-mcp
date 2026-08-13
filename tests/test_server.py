"""Tests for MCP server wiring: tool registration, lifespan, error masking."""

from __future__ import annotations

import pytest

from fastapi_docs_mcp import http, server


class TestServer:
    async def test_tools_registered(self) -> None:
        registered = {tool.name for tool in await server.mcp.list_tools()}
        assert "get_fastapi_docs" in registered
        assert len(registered) == 6

    async def test_lifespan_closes_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed = False

        async def fake_aclose() -> None:
            nonlocal closed
            closed = True

        monkeypatch.setattr(http, "aclose", fake_aclose)
        async with server._lifespan(server.mcp):
            pass
        assert closed

    def test_mask_error_details_enabled(self) -> None:
        # Regression guard: only deliberately authored ToolError messages
        # should reach the client; unanticipated exceptions must be masked.
        assert server.mcp._mask_error_details is True
