"""Live, network-dependent contract tests (opt-in: `uv run pytest -m integration`).

These hit the real fastapi.tiangolo.com / raw.githubusercontent.com upstreams —
run on a schedule by `.github/workflows/canary.yml` to catch upstream drift
(sitemap format, include-directive syntax, markdown paths) that the mocked
unit tests can't see.
"""

from __future__ import annotations

import pytest

from fastapi_docs_mcp import sitemap, tools
from fastapi_docs_mcp.config import BASE_URL


@pytest.mark.integration
class TestLive:
    async def test_live_docs(self) -> None:
        out = await tools.get_fastapi_docs("tutorial/first-steps")
        assert "FastAPI" in out

    async def test_live_sitemap(self) -> None:
        urls = await sitemap.fetch_sitemap()
        assert urls and all(u.startswith(BASE_URL) for u in urls)
