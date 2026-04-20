"""JWKS fetcher with in-memory cache + stale-while-revalidate.

Fetches the JWKS document from ``settings.auth_jwks_url`` (by default
``https://auth.bridgingchina.net/api/auth/jwks``) and caches it in a
module-level dict.

Cache semantics
---------------
- Fresh for 1 hour (``_CACHE_TTL_SECONDS``): return cached payload without
  hitting the network.
- Stale-while-revalidate for up to 2 hours (``_STALE_TTL_SECONDS``): if the
  cache is older than fresh TTL but newer than stale TTL, attempt a refetch;
  on network failure, serve the stale cached copy instead of erroring.
- Older than stale TTL or never populated + network failure: raise.
- Cold-cache thundering-herd guard: a single module-level ``asyncio.Lock``
  serialises concurrent first-time fetches; the second coroutine re-checks
  the cache under the lock before issuing its own network call.
- Rotation refetch on unknown kid: ``get_key_for_kid`` force-refreshes once
  (subject to a 60-second cooldown) when the requested kid is absent, so
  callers see an at-most-60s rotation outage instead of waiting for the
  full 1h TTL.

The cache is deliberately process-local (not Redis / shared) — the upstream
auth Worker is CDN-backed and rate limits are generous, so the single-process
cache is sufficient even under multi-worker uvicorn.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.core.config import settings

_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_CACHE_TTL_SECONDS = 3600  # 1 hour fresh
_STALE_TTL_SECONDS = 7200  # serve stale for 2 hours if fetch fails

_fetch_lock = asyncio.Lock()

_last_refetch_on_miss: float = 0.0
_REFETCH_ON_MISS_COOLDOWN_SECONDS = 60


async def get_jwks() -> dict[str, Any]:
    """Return JWKS dict. Cache fresh for 1h, stale-while-revalidate up to 2h.

    Raises any ``httpx`` / network error only when the cache has never been
    populated or is older than ``_STALE_TTL_SECONDS``.

    Concurrent first-time callers are serialised through ``_fetch_lock`` —
    the second coroutine re-checks the cache under the lock (double-checked
    locking) to avoid burning N redundant upstream fetches in the first
    second after boot.
    """
    now = time.time()
    cached = _cache["keys"]
    age = now - _cache["fetched_at"]

    if cached is not None and age < _CACHE_TTL_SECONDS:
        return cached

    async with _fetch_lock:
        # Re-check under the lock: another coroutine may have just filled
        # the cache while we were waiting.
        now = time.time()
        cached = _cache["keys"]
        age = now - _cache["fetched_at"]
        if cached is not None and age < _CACHE_TTL_SECONDS:
            return cached

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(settings.auth_jwks_url)
                resp.raise_for_status()
                data = resp.json()
                _cache["keys"] = data
                _cache["fetched_at"] = now
                return data
        except Exception:
            if cached is not None and age < _STALE_TTL_SECONDS:
                return cached  # stale-while-revalidate
            raise


async def get_key_for_kid(kid: str) -> dict[str, Any] | None:
    """Fetch JWKS + return the key entry matching ``kid``, or ``None``.

    If the kid is not in the cached JWKS, force a single refetch (bounded
    by ``_REFETCH_ON_MISS_COOLDOWN_SECONDS``) to pick up a just-rotated key.
    The cooldown prevents an attacker from triggering unbounded upstream
    fetches by spamming tokens with fabricated kid headers.
    """
    jwks = await get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key

    # Unknown kid: this may be an auth-Worker rotation. Force a refetch
    # (rate-limited) and retry once.
    global _last_refetch_on_miss
    now = time.time()
    if now - _last_refetch_on_miss > _REFETCH_ON_MISS_COOLDOWN_SECONDS:
        _last_refetch_on_miss = now
        _cache["fetched_at"] = 0.0  # invalidate so get_jwks refetches
        jwks = await get_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
    return None


def _reset_cache_for_tests() -> None:
    """Test-only helper: clear the module-level cache."""
    global _last_refetch_on_miss
    _cache["keys"] = None
    _cache["fetched_at"] = 0.0
    _last_refetch_on_miss = 0.0
