"""Task-level LLM router — ``task_key → (Provider, model_id)`` with TTL cache.

Phase C of the Multi-Provider + Task-Level Model Routing refactor. Services
call :func:`get_for_task` (or more usually :func:`app.llm.chat_for_task`) with
a logical task key like ``"qa_generation"`` / ``"ingest_tagger"`` and get back
the concrete provider instance + upstream model id.

The 30-second TTL cache is a deliberate trade-off: admin edits to
``llm_task_routes`` propagate within 30s *without* requiring a process-wide
invalidation broadcast. Phase D's admin endpoint should still call
:func:`invalidate` on write for zero-latency updates; the TTL is a fallback
so mis-sequenced invalidations (multi-worker deploys, forgotten callsites)
self-heal.

TTL is deliberately NOT configurable at this stage — YAGNI. Phase D/E may
expose it via settings if ops needs finer control.
"""
import threading
import time

from app.core.database import SessionLocal
from app.llm.registry import _registry
from app.models.llm import LLMProviderRow, LLMTaskRoute
from app.providers.base import LLMProvider
from app.providers.config import ProviderConfig
from app.providers.errors import TaskRouteNotFoundError

_ROUTE_CACHE: dict[str, tuple[float, LLMProvider, str]] = {}
_ROUTE_LOCK = threading.Lock()
_TTL_SECONDS = 30.0


def get_for_task(task_key: str) -> tuple[LLMProvider, str]:
    """Resolve ``task_key`` to a concrete ``(Provider, model_id)`` pair.

    Cache hit path (hot): a single dict lookup + lock acquire.
    Cache miss path: one DB roundtrip joining ``llm_task_routes`` against
    ``llm_providers``, then delegating to :class:`ProviderRegistry` for the
    actual provider instance.

    Raises :class:`TaskRouteNotFoundError` (subclass of ``ProviderError``) when
    no row exists for the given task_key — this is a deploy-time bug (missing
    seed), not a user-facing condition, and should surface as HTTP 500.
    """
    now = time.monotonic()
    with _ROUTE_LOCK:
        entry = _ROUTE_CACHE.get(task_key)
        if entry is not None and entry[0] > now:
            return entry[1], entry[2]

    # Cache miss or expired — fetch from DB outside the lock so concurrent
    # cold lookups for DIFFERENT task_keys don't serialise.
    with SessionLocal() as db:
        row = (
            db.query(LLMTaskRoute, LLMProviderRow)
            .join(LLMProviderRow, LLMTaskRoute.provider_id == LLMProviderRow.id)
            .filter(LLMTaskRoute.task_key == task_key)
            .first()
        )
    if row is None:
        raise TaskRouteNotFoundError(
            f"no llm_task_routes row for task_key={task_key}"
        )

    route, provider_row = row
    config = ProviderConfig(
        provider_id=str(provider_row.id),
        kind=provider_row.kind,
        base_url=provider_row.base_url,
        api_key_env=provider_row.api_key_env,
        extra_headers=provider_row.extra_headers or {},
        timeout_read=provider_row.timeout_read,
    )
    provider = _registry.get_or_build(config)

    with _ROUTE_LOCK:
        _ROUTE_CACHE[task_key] = (now + _TTL_SECONDS, provider, route.model_id)

    return provider, route.model_id


def invalidate(task_key: str) -> None:
    """Drop a specific task_key's cache entry. Phase D write endpoints call this."""
    with _ROUTE_LOCK:
        _ROUTE_CACHE.pop(task_key, None)


def invalidate_all() -> None:
    """Drop every cached route. Intended for test isolation and config reloads."""
    with _ROUTE_LOCK:
        _ROUTE_CACHE.clear()
