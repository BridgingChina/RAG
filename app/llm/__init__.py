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
"""
from app.core.config import settings
from app.llm.registry import _registry
from app.llm.router import get_for_task, invalidate as invalidate_task, invalidate_all
from app.providers import get_provider as _legacy_get_provider
from app.providers.base import ChatMessage, ChatResponse


async def chat_for_task(
    task_key: str, messages: list[ChatMessage]
) -> ChatResponse:
    """Issue a chat completion routed by ``task_key``.

    Looks up the configured ``(provider, model)`` for the task, delegates to
    the provider's ``chat()`` with the exact model id. All existing retry /
    timeout / error-wrapping behavior on the provider is preserved —
    :func:`chat_for_task` is a thin dispatcher, nothing more.
    """
    provider, model_id = get_for_task(task_key)
    return await provider.chat(messages, model=model_id)


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
