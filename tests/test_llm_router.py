"""Unit tests for :mod:`app.llm.router` — task-level routing + TTL cache.

DB-touching tests are marked ``integration`` via the fixture; pure cache-logic
tests run without a DB.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.llm import router
from app.llm.registry import _registry
from app.providers.base import LLMProvider
from app.providers.config import ProviderConfig
from app.providers.errors import TaskRouteNotFoundError


@pytest.fixture(autouse=True)
def _reset_router_state():
    """Every test starts with an empty route cache and a fresh registry."""
    router.invalidate_all()
    _registry.invalidate_all()
    yield
    router.invalidate_all()
    _registry.invalidate_all()


# --- Pure cache-logic tests (no DB) --------------------------------------


class _DummyProvider(LLMProvider):
    async def embed(self, texts, *, model=None):
        return []

    async def chat(self, messages, *, model=None):
        return None

    async def chat_stream(self, messages, *, model=None):
        if False:
            yield ""

    async def list_models(self):
        return []


def _seed_cache_entry(task_key: str, model_id: str, ttl: float = 30.0):
    """Directly poke the router cache for tests that don't want a DB trip."""
    provider = _DummyProvider()
    now = time.monotonic()
    router._ROUTE_CACHE[task_key] = (now + ttl, provider, model_id)
    return provider


def test_cache_hit_returns_seeded_entry():
    provider = _seed_cache_entry("qa_generation", "glm-4.7")
    p, model = router.get_for_task("qa_generation")
    assert p is provider
    assert model == "glm-4.7"


def test_invalidate_clears_single_entry():
    _seed_cache_entry("qa_generation", "glm-4.7")
    _seed_cache_entry("ingest_tagger", "glm-4.7")
    router.invalidate("qa_generation")
    assert "qa_generation" not in router._ROUTE_CACHE
    # Sibling entry untouched.
    assert "ingest_tagger" in router._ROUTE_CACHE


def test_invalidate_all_clears_every_entry():
    _seed_cache_entry("qa_generation", "glm-4.7")
    _seed_cache_entry("ingest_tagger", "glm-4.7")
    router.invalidate_all()
    assert router._ROUTE_CACHE == {}


def test_ttl_expiry_triggers_refetch(monkeypatch):
    """When the cache TTL has elapsed, ``get_for_task`` must re-fetch.

    We stub out :func:`SessionLocal` so the miss path doesn't touch a real DB —
    instead it raises ``TaskRouteNotFoundError`` (no seeded row), and we
    assert that the miss path WAS entered. That's sufficient proof of TTL
    honouring without needing a live DB.
    """
    _seed_cache_entry("stale_task", "glm-x", ttl=-1.0)  # Expired immediately.

    # Stub SessionLocal to yield a session whose query returns None.
    fake_db = MagicMock()
    fake_db.__enter__ = lambda self=fake_db: self
    fake_db.__exit__ = lambda self, exc_type, exc, tb: False
    fake_db.query.return_value.join.return_value.filter.return_value.first.return_value = None

    def _fake_session_local():
        return fake_db

    monkeypatch.setattr(router, "SessionLocal", _fake_session_local)

    # Expired cache entry + no DB row → miss path + TaskRouteNotFoundError.
    with pytest.raises(TaskRouteNotFoundError):
        router.get_for_task("stale_task")


def test_missing_route_raises(monkeypatch):
    fake_db = MagicMock()
    fake_db.__enter__ = lambda self=fake_db: self
    fake_db.__exit__ = lambda self, exc_type, exc, tb: False
    fake_db.query.return_value.join.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(router, "SessionLocal", lambda: fake_db)

    with pytest.raises(TaskRouteNotFoundError):
        router.get_for_task("no_such_task_key")


# --- Registry smoke test --------------------------------------------------


def test_registry_builds_zhipu_once_per_id():
    config = ProviderConfig(
        provider_id=str(uuid4()),
        kind="zhipu",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_env="ZHIPU_API_KEY",
        extra_headers={},
        timeout_read=90.0,
    )
    instance_a = _registry.get_or_build(config)
    instance_b = _registry.get_or_build(config)
    assert instance_a is instance_b  # Cache hit, same object.


def test_registry_unknown_kind_raises():
    from app.providers.errors import ProviderConfigurationError

    config = ProviderConfig(
        provider_id=str(uuid4()),
        kind="not_a_real_kind",
        base_url="",
        api_key_env="X",
    )
    with pytest.raises(ProviderConfigurationError):
        _registry.get_or_build(config)
