"""Tests for the single network choke point: allowlist, size cap, error mapping."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from fastapi_docs_mcp import http
from fastapi_docs_mcp.config import BASE_URL


class _FakeStream:
    def __init__(
        self,
        *,
        url: str = f"{BASE_URL}/x",
        chunks: tuple[bytes, ...] = (b"hello",),
        raise_status: Exception | None = None,
        enter_exc: Exception | None = None,
    ) -> None:
        self.url = httpx.URL(url)
        self.encoding = "utf-8"
        self._chunks = chunks
        self._raise_status = raise_status
        self._enter_exc = enter_exc

    async def __aenter__(self) -> _FakeStream:
        if self._enter_exc is not None:
            raise self._enter_exc
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self._raise_status is not None:
            raise self._raise_status

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def _patch_client(monkeypatch: pytest.MonkeyPatch, stream: _FakeStream) -> None:
    class _FakeClient:
        is_closed = False

        def stream(self, _method: str, _url: str) -> _FakeStream:
            return stream

    monkeypatch.setattr(http, "get_client", lambda: _FakeClient())


def _status_error(status: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        str(status),
        request=httpx.Request("GET", f"{BASE_URL}/x"),
        response=httpx.Response(status),
    )


class TestHttp:
    def test_host_allowed(self) -> None:
        assert http._host_allowed("https://fastapi.tiangolo.com/x")
        assert http._host_allowed("https://raw.githubusercontent.com/y")
        assert not http._host_allowed("https://evil.com/z")

    async def test_download_rejects_disallowed_host(self) -> None:
        assert await http._download("https://evil.com/x") is None

    async def test_download_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_client(monkeypatch, _FakeStream(chunks=(b"abc", b"def")))
        assert await http._download(f"{BASE_URL}/ok") == "abcdef"

    async def test_download_redirect_off_allowlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(url="https://evil.com/redirected"))
        assert await http._download(f"{BASE_URL}/ok") is None

    async def test_download_size_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("fastapi_docs_mcp.http.MAX_DOWNLOAD_BYTES", 4)
        _patch_client(monkeypatch, _FakeStream(chunks=(b"aaaa", b"bbbb")))
        # First chunk (4 bytes) is within cap; second pushes over and is dropped.
        assert await http._download(f"{BASE_URL}/big") == "aaaa"

    async def test_download_confirmed_404_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(raise_status=_status_error(404)))
        assert await http._download(f"{BASE_URL}/missing") is None

    async def test_download_timeout_raises_upstream_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(enter_exc=httpx.TimeoutException("t")))
        with pytest.raises(http.UpstreamError):
            await http._download(f"{BASE_URL}/slow")

    async def test_download_5xx_raises_upstream_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(raise_status=_status_error(503)))
        with pytest.raises(http.UpstreamError):
            await http._download(f"{BASE_URL}/flaky")

    async def test_download_generic_error_raises_upstream_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_client(monkeypatch, _FakeStream(enter_exc=httpx.HTTPError("boom")))
        with pytest.raises(http.UpstreamError):
            await http._download(f"{BASE_URL}/err")

    async def test_fetch_uses_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = 0

        async def fake_download(_url: str) -> str:
            nonlocal calls
            calls += 1
            return "payload"

        monkeypatch.setattr(http, "_download", fake_download)
        assert await http.fetch(f"{BASE_URL}/c") == "payload"
        assert await http.fetch(f"{BASE_URL}/c") == "payload"
        assert calls == 1

    async def test_fetch_propagates_upstream_error_uncached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        async def fake_download(_url: str) -> str:
            nonlocal calls
            calls += 1
            raise http.UpstreamError("nope")

        monkeypatch.setattr(http, "_download", fake_download)
        with pytest.raises(http.UpstreamError):
            await http.fetch(f"{BASE_URL}/flaky")
        # A failed fetch must not be cached, so a retry hits the network again.
        with pytest.raises(http.UpstreamError):
            await http.fetch(f"{BASE_URL}/flaky")
        assert calls == 2

    async def test_get_client_singleton(self) -> None:
        c1 = http.get_client()
        c2 = http.get_client()
        assert c1 is c2
        await http.aclose()
        assert http._client is None
