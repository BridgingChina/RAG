"""Unit tests for :func:`app.llm.chat_stream_for_task` — streaming variant of chat_for_task.

Stubs the router resolution (``app.llm.get_for_task``) so no DB is required —
mirrors the pattern in ``test_llm_call_logging.py``. The streaming variant must
delegate to ``provider.chat_stream(messages, model=<routed model>)`` and yield
each token unchanged.
"""
from __future__ import annotations

import pytest

from app.llm import chat_stream_for_task
from app.providers.base import ChatMessage, LLMProvider


class _StubStreamProvider(LLMProvider):
    """Minimal provider whose ``chat_stream`` yields a fixed token list."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.received_model: str | None = None
        self.received_messages: list[ChatMessage] | None = None

    async def embed(self, texts, *, model=None):  # pragma: no cover — unused
        return []

    async def chat(self, messages, *, model=None):  # pragma: no cover — unused
        raise NotImplementedError

    async def chat_stream(self, messages, *, model=None):
        self.received_messages = messages
        self.received_model = model
        for tok in self._tokens:
            yield tok

    async def list_models(self):  # pragma: no cover — unused
        return []


@pytest.mark.asyncio
async def test_chat_stream_for_task_routes_via_provider(monkeypatch):
    """chat_stream_for_task resolves task_key, then yields provider tokens unchanged."""
    provider = _StubStreamProvider(["hello", " world"])
    monkeypatch.setattr(
        "app.llm.get_for_task", lambda task_key: (provider, "glm-4.7")
    )

    messages = [ChatMessage(role="user", content="hi")]
    tokens = [
        tok async for tok in chat_stream_for_task("qa_generation", messages)
    ]

    assert tokens == ["hello", " world"]
    # Confirm the routed model was forwarded to the provider unchanged.
    assert provider.received_model == "glm-4.7"
    assert provider.received_messages is messages
