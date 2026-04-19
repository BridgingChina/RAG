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

The cache is deliberately process-local (not Redis / shared) — the upstream
auth Worker is CDN-backed and rate limits are generous, so the single-process
cache is sufficient even under multi-worker uvicorn.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings

_cache: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_CACHE_TTL_SECONDS = 3600  # 1 hour fresh
_STALE_TTL_SECONDS = 7200  # serve stale for 2 hours if fetch fails


async def get_jwks() -> dict[str, Any]:
    """Return JWKS dict. Cache fresh for 1h, stale-while-revalidate up to 2h.

    Raises any ``httpx`` / network error only when the cache has never been
    populated or is older than ``_STALE_TTL_SECONDS``.
    """
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
    """Fetch JWKS + return the key entry matching ``kid``, or ``None``."""
    jwks = await get_jwks()
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


def _reset_cache_for_tests() -> None:
    """Test-only helper: clear the module-level cache."""
    _cache["keys"] = None
    _cache["fetched_at"] = 0.0
