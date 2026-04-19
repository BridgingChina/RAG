"""Tests for app.services.jwks_client."""
from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services import jwks_client
from app.services.jwks_client import (
    _CACHE_TTL_SECONDS,
    _REFETCH_ON_MISS_COOLDOWN_SECONDS,
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


# ---------------------------------------------------------------------------
# Rotation refetch on unknown kid (I2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_key_for_kid_force_refetches_on_unknown_kid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a kid isn't in the cached JWKS, we should refetch once so that
    an auth-Worker key rotation doesn't cause a ~1h outage."""
    old_jwks: dict[str, Any] = {
        "keys": [
            {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "kid": "old", "x": "AAA"}
        ]
    }
    new_jwks: dict[str, Any] = {
        "keys": [
            {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "kid": "new", "x": "BBB"}
        ]
    }

    call_count = {"n": 0}

    def factory_factory(*args: Any, **kwargs: Any) -> MagicMock:
        # Factory returns a fresh MagicMock each time AsyncClient() is called.
        call_count["n"] += 1
        # First call -> old JWKS, subsequent -> new JWKS.
        response_json = old_jwks if call_count["n"] == 1 else new_jwks

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value=response_json)
        mock_response.raise_for_status = MagicMock()

        async def mock_get(url: str) -> Any:
            return mock_response

        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=mock_get)

        async def aenter(self: Any) -> Any:
            return mock_client

        async def aexit(self: Any, *args: Any) -> None:
            return None

        cm = MagicMock()
        cm.__aenter__ = aenter
        cm.__aexit__ = aexit
        return cm

    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory_factory)

    # Populate cache with the old JWKS.
    first_key = await get_key_for_kid("old")
    assert first_key is not None
    assert first_key["kid"] == "old"
    assert call_count["n"] == 1

    # Ask for the NEW kid. Cache still has only "old" → should refetch.
    new_key = await get_key_for_kid("new")
    assert new_key is not None
    assert new_key["kid"] == "new"
    # Exactly 2 fetches total: initial + force-refetch on miss.
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_get_key_for_kid_respects_refetch_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second unknown kid within the cooldown window must NOT trigger a
    second refetch — otherwise an attacker can DoS the auth Worker by
    submitting tokens with fabricated kid headers."""
    jwks_with_old: dict[str, Any] = {
        "keys": [
            {"kty": "OKP", "crv": "Ed25519", "alg": "EdDSA", "kid": "only", "x": "AAA"}
        ]
    }
    # Always return the same JWKS — neither requested kid exists.
    factory = _build_mock_async_client(response_json=jwks_with_old)
    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    # 1st call: populates cache (1 fetch).
    assert await get_key_for_kid("only") is not None
    assert factory.call_count == 1

    # 2nd call: unknown kid → triggers refetch (2 total).
    assert await get_key_for_kid("unknown-1") is None
    assert factory.call_count == 2

    # 3rd call: different unknown kid, still within cooldown → NO refetch.
    assert await get_key_for_kid("unknown-2") is None
    assert factory.call_count == 2

    # After the cooldown elapses, another unknown kid should refetch again.
    jwks_client._last_refetch_on_miss = (
        time.time() - _REFETCH_ON_MISS_COOLDOWN_SECONDS - 1
    )
    assert await get_key_for_kid("unknown-3") is None
    assert factory.call_count == 3


# ---------------------------------------------------------------------------
# Thundering-herd protection (M4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_cold_fetches_trigger_single_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N concurrent get_jwks() calls on a cold cache should all share a
    single upstream fetch thanks to the double-checked asyncio.Lock."""
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()
    call_count = {"n": 0}

    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=SAMPLE_JWKS)
    mock_response.raise_for_status = MagicMock()

    async def mock_get(url: str) -> Any:
        call_count["n"] += 1
        fetch_started.set()
        # Block inside the fetch so that other coroutines have a chance to
        # reach the lock and queue behind us.
        await release_fetch.wait()
        return mock_response

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=mock_get)

    async def aenter(self: Any) -> Any:
        return mock_client

    async def aexit(self: Any, *args: Any) -> None:
        return None

    def factory(*args: Any, **kwargs: Any) -> Any:
        cm = MagicMock()
        cm.__aenter__ = aenter
        cm.__aexit__ = aexit
        return cm

    monkeypatch.setattr(jwks_client.httpx, "AsyncClient", factory)

    # Kick off 5 concurrent cold fetches.
    tasks = [asyncio.create_task(get_jwks()) for _ in range(5)]

    # Wait until the first task is inside the httpx call.
    await fetch_started.wait()
    # Give the other tasks a chance to enqueue on the lock.
    await asyncio.sleep(0.01)

    # Release the first fetch so everyone can finish.
    release_fetch.set()
    results = await asyncio.gather(*tasks)

    assert all(r == SAMPLE_JWKS for r in results)
    # Only ONE underlying network call across all 5 coroutines.
    assert call_count["n"] == 1
