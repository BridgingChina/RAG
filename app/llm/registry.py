"""Provider registry — caches LLMProvider instances keyed by DB provider_id.

Phase C of the Multi-Provider + Task-Level Model Routing refactor. The registry
is a module-level singleton that the :mod:`app.llm.router` consults when it
needs a concrete provider instance for a given ``ProviderConfig``.

Thread-safety: ``_cache`` mutation is guarded by ``threading.Lock`` — provider
instances themselves are immutable w.r.t. the cache (we never re-build one
over a running instance), so readers that raced a cache miss will each see a
consistent instance after the lock is released.

Invalidation: :meth:`invalidate` / :meth:`invalidate_all` drop cached instances.
Phase D's admin provider-edit endpoint must call ``invalidate`` on the edited
provider_id after commit so the next :func:`router.get_for_task` rebuilds the
instance with fresh config.
"""
import threading

from app.providers.base import LLMProvider
from app.providers.config import ProviderConfig
from app.providers.errors import ProviderConfigurationError
from app.providers.minimax import MiniMaxProvider
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.zhipu import ZhipuProvider


class ProviderRegistry:
    """Caches Provider instances keyed by ``provider_id`` (DB UUID as str)."""

    def __init__(self) -> None:
        self._cache: dict[str, LLMProvider] = {}
        self._lock = threading.Lock()

    def get_or_build(self, config: ProviderConfig) -> LLMProvider:
        pid = str(config.provider_id)
        with self._lock:
            instance = self._cache.get(pid)
            if instance is not None:
                return instance
            if config.kind == "zhipu":
                # ZhipuProvider reads settings directly; config is advisory.
                # Kept so Phase B's schema row + api_key_env conventions carry
                # through even though the concrete instance ignores the rest.
                instance = ZhipuProvider()
            elif config.kind == "openai_compat":
                instance = OpenAICompatProvider(config)
            elif config.kind == "minimax":
                instance = MiniMaxProvider(config)
            else:
                raise ProviderConfigurationError(
                    f"unknown provider kind: {config.kind}"
                )
            self._cache[pid] = instance
            return instance

    def invalidate(self, provider_id: str) -> None:
        with self._lock:
            self._cache.pop(str(provider_id), None)

    def invalidate_all(self) -> None:
        with self._lock:
            self._cache.clear()


# Module-level singleton. Tests that want isolation can call
# ``_registry.invalidate_all()`` in a fixture.
_registry = ProviderRegistry()
