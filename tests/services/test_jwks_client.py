"""Tests for app.services.jwks_client."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services import jwks_client
from app.services.jwks_client import (
    _CACHE_TTL_SECONDS,
    _STALE_TTL_SECONDS,
    _reset_cache_for_tests,
    get_jwks,
    get_key_for_kid,
)


SAMPLE_JWKS: dict[str, Any] = {
    "keys": [
        {
            "alg": "EdDSA",
            "crv": "Ed25519",
            "kty": "OKP",
            "x": "NpuQR8L5H9m8iDbP07r3luLS-neJvSs67NJeWxDxAys",
            "kid": "test-kid-1",
        },
        {
            "alg": "EdDSA",
            "crv": "Ed25519",
            "kty": "OKP",
            "x": "AAAAR8L5H9m8iDbP07r3luLS-neJvSs67NJeWxDxAys",
            "kid": "test-kid-2",
        },
    ]
}


@pytest.fixture(autouse=True)
def _clear_cache():
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


def _build_mock_async_client(
    response_json: Any = None, raise_error: Exception | None = None
) -> MagicMock:
    """Return a MagicMock replacement for httpx.AsyncClient that yields a
    client whose .get() returns a mock response (or raises)."""
    mock_response = MagicMock()
    if raise_error is None:
        mock_response.json = MagicMock(return_value=response_json)
        mock_response.raise_for_status = MagicMock()

    async def mock_get(url: str) -> Any:
        if raise_error is not None:
            raise raise_error
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=mock_get)

    # AsyncClient() returns a context manager — async __aenter__/__aexit__
    async def aenter(self: Any) -> Any:
        return mock_client

    async def aexit(self: Any, *args: Any) -> None:
        return None

    cm = MagicMock()
    cm.__aenter__ = aenter
    cm.__aexit__ = aexit

    factory = MagicMock(return_value=cm)
    return factory


@pytest.mark.asyncio
async def test_fresh_fetch_populates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    result = await get_jwks()
    assert result == SAMPLE_JWKS
    assert jwks_client._cache["keys"] == SAMPLE_JWKS
    assert jwks_client._cache["fetched_at"] > 0
    assert factory.call_count == 1


@pytest.mark.asyncio
async def test_cache_hit_within_fresh_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    first = await get_jwks()
    second = await get_jwks()
    assert first == second == SAMPLE_JWKS
    # Only one network call should have been made.
    assert factory.call_count == 1


@pytest.mark.asyncio
async def test_cache_miss_after_ttl_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    await get_jwks()
    assert factory.call_count == 1

    # Backdate the cache to be older than fresh TTL (but younger than stale).
    jwks_client._cache["fetched_at"] = time.time() - (_CACHE_TTL_SECONDS + 10)

    await get_jwks()
    assert factory.call_count == 2


@pytest.mark.asyncio
async def test_stale_while_revalidate_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # First fetch succeeds and populates cache.
    ok_factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", ok_factory)
    await get_jwks()

    # Age the cache past fresh TTL but within stale TTL.
    jwks_client._cache["fetched_at"] = time.time() - (_CACHE_TTL_SECONDS + 60)

    # Next fetch fails — expect stale data to be served.
    fail_factory = _build_mock_async_client(
        raise_error=httpx.ConnectError("DNS broken")
    )
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", fail_factory)

    result = await get_jwks()
    assert result == SAMPLE_JWKS


@pytest.mark.asyncio
async def test_raises_when_cache_empty_and_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fail_factory = _build_mock_async_client(
        raise_error=httpx.ConnectError("DNS broken")
    )
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", fail_factory)

    with pytest.raises(httpx.ConnectError):
        await get_jwks()


@pytest.mark.asyncio
async def test_raises_when_stale_ttl_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok_factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", ok_factory)
    await get_jwks()

    # Age the cache past stale TTL entirely.
    jwks_client._cache["fetched_at"] = time.time() - (_STALE_TTL_SECONDS + 60)

    fail_factory = _build_mock_async_client(
        raise_error=httpx.ConnectError("DNS broken")
    )
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", fail_factory)

    with pytest.raises(httpx.ConnectError):
        await get_jwks()


@pytest.mark.asyncio
async def test_get_key_for_kid_returns_match(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    key = await get_key_for_kid("test-kid-2")
    assert key is not None
    assert key["kid"] == "test-kid-2"


@pytest.mark.asyncio
async def test_get_key_for_kid_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory = _build_mock_async_client(response_json=SAMPLE_JWKS)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    key = await get_key_for_kid("does-not-exist")
    assert key is None
