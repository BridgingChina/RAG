"""High-level LLM routing helpers — the single entry point every call site uses.

Phase C of the Multi-Provider + Task-Level Model Routing refactor. Instead of
``provider = get_provider(); await provider.chat(...)``, every business-logic
call site imports :func:`chat_for_task` and names the task it is performing:

    from app.llm import chat_for_task
    response = await chat_for_task("qa_generation", messages)

The router (:mod:`app.llm.router`) resolves ``task_key`` against the seeded
``llm_task_routes`` table and returns the appropriate provider + model.

Embedding calls (:func:`embed`) remain locked to Zhipu's ``embedding-3`` per
design §2: the 1024-d vector space of the existing corpus is the architectural
invariant, and multi-provider embedding would require reindex-migrations far
beyond Phase C's scope.

Phase F adds one structured ``llm_call`` log line per :func:`chat_for_task`
invocation (INFO on success, WARNING on failure) so Grafana/Loki JSON parsers
can chart latency / failure rates per task_key + provider + model.
"""
import logging
import time

from app.core.config import settings
from app.llm.registry import _registry
from app.llm.router import get_for_task, invalidate as invalidate_task, invalidate_all
from app.providers import get_provider as _legacy_get_provider
from app.providers._sanitize import sanitize_error
from app.providers.base import ChatMessage, ChatResponse

logger = logging.getLogger(__name__)


async def chat_for_task(
    task_key: str, messages: list[ChatMessage]
) -> ChatResponse:
    """Issue a chat completion routed by ``task_key``.

    Looks up the configured ``(provider, model)`` for the task, delegates to
    the provider's ``chat()`` with the exact model id. All existing retry /
    timeout / error-wrapping behavior on the provider is preserved —
    :func:`chat_for_task` is a thin dispatcher, nothing more.

    Emits one ``llm_call`` structured log record per invocation:
    INFO on success, WARNING on failure. Failure ``reason`` is sanitized by
    :func:`sanitize_error` so logs cannot leak provider API keys.
    """
    provider, model_id = get_for_task(task_key)
    provider_id = (
        provider._config.provider_id if hasattr(provider, "_config") else None
    )
    start = time.monotonic()
    try:
        resp = await provider.chat(messages, model=model_id)
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "llm_call",
            extra={
                "event": "llm_call",
                "task_key": task_key,
                "provider_id": provider_id,
                "provider_class": provider.__class__.__name__,
                "model_id": model_id,
                "status": "fail",
                "latency_ms": latency_ms,
                "failure_reason": sanitize_error(exc),
            },
        )
        raise

    latency_ms = int((time.monotonic() - start) * 1000)
    usage = resp.usage if isinstance(resp.usage, dict) else {}
    logger.info(
        "llm_call",
        extra={
            "event": "llm_call",
            "task_key": task_key,
            "provider_id": provider_id,
            "provider_class": provider.__class__.__name__,
            "model_id": model_id,
            "status": "ok",
            "latency_ms": latency_ms,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "retry_attempts": 0,  # tenacity doesn't surface attempts here — v2 wrap
            "failure_reason": None,
        },
    )
    return resp


async def embed(texts: list[str]) -> list[list[float]]:
    """Embedding — intentionally **not** task-routed.

    Design §2 commits the corpus to Zhipu ``embedding-3`` (1024-d). Allowing
    admins to switch embedding providers at runtime would invalidate every
    vector in ``chunks.embedding`` without a concurrent reindex — a disaster
    waiting to happen. Phase C keeps this single non-routed call-path; any
    future multi-embedder story is a separate design exercise.
    """
    return await _legacy_get_provider().embed(
        texts, model=settings.embedding_model
    )


__all__ = [
    "ChatMessage",
    "ChatResponse",
    "chat_for_task",
    "embed",
    "get_for_task",
    "invalidate_task",
    "invalidate_all",
]
