"""Unit tests for Phase F1 — `llm_call` structured log emission.

:func:`app.llm.chat_for_task` must emit exactly one log record per call with
``event == "llm_call"``. Success → INFO with ``status == "ok"`` + latency +
token fields; failure → WARNING with ``status == "fail"`` + sanitized
``failure_reason``, and the exception must still propagate.

Tests stub the router so no DB is required.
"""
from __future__ import annotations

import logging
import time

import pytest

from app.llm import chat_for_task
from app.providers.base import ChatMessage, ChatResponse, LLMProvider
from app.providers.errors import ProviderUnavailableError


class _DummyProvider(LLMProvider):
    """Minimal provider; ``chat`` is overridden per test via monkeypatch."""

    async def embed(self, texts, *, model=None):
        return []

    async def chat(self, messages, *, model=None):  # pragma: no cover — overridden
        raise NotImplementedError

    async def list_models(self):
        return []


def _find_llm_call_record(
    records: list[logging.LogRecord],
) -> logging.LogRecord:
    llm_records = [r for r in records if getattr(r, "event", None) == "llm_call"]
    assert len(llm_records) == 1, (
        f"expected exactly one llm_call record, got {len(llm_records)}: "
        f"{[r.getMessage() for r in records]}"
    )
    return llm_records[0]


@pytest.mark.asyncio
async def test_chat_for_task_emits_llm_call_log_on_success(
    monkeypatch, caplog
):
    """Success path writes INFO record with status=ok + latency + token fields."""
    provider = _DummyProvider()

    async def _fake_chat(self, messages, *, model=None):
        return ChatResponse(
            content="hello",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            model=model or "",
        )

    # Stub router resolution so we don't need a DB.
    monkeypatch.setattr(
        "app.llm.get_for_task", lambda task_key: (provider, "glm-4.7")
    )
    monkeypatch.setattr(_DummyProvider, "chat", _fake_chat)

    caplog.set_level(logging.INFO, logger="app.llm")
    resp = await chat_for_task(
        "qa_generation", [ChatMessage(role="user", content="ping")]
    )

    assert resp.content == "hello"

    record = _find_llm_call_record(caplog.records)
    assert record.levelno == logging.INFO
    assert record.event == "llm_call"
    assert record.task_key == "qa_generation"
    assert record.provider_class == "_DummyProvider"
    assert record.model_id == "glm-4.7"
    assert record.status == "ok"
    assert isinstance(record.latency_ms, int)
    assert record.latency_ms >= 0
    assert record.prompt_tokens == 10
    assert record.completion_tokens == 5
    assert record.failure_reason is None


@pytest.mark.asyncio
async def test_chat_for_task_emits_llm_call_log_on_failure(
    monkeypatch, caplog
):
    """Failure path writes WARNING with sanitized reason; exception propagates."""
    provider = _DummyProvider()

    async def _fake_chat(self, messages, *, model=None):
        raise ProviderUnavailableError("upstream 502")

    monkeypatch.setattr(
        "app.llm.get_for_task", lambda task_key: (provider, "glm-4.7")
    )
    monkeypatch.setattr(_DummyProvider, "chat", _fake_chat)

    caplog.set_level(logging.INFO, logger="app.llm")

    with pytest.raises(ProviderUnavailableError):
        await chat_for_task(
            "qa_generation", [ChatMessage(role="user", content="ping")]
        )

    record = _find_llm_call_record(caplog.records)
    assert record.levelno == logging.WARNING
    assert record.event == "llm_call"
    assert record.status == "fail"
    assert record.task_key == "qa_generation"
    assert record.provider_class == "_DummyProvider"
    assert record.model_id == "glm-4.7"
    assert isinstance(record.latency_ms, int)
    assert record.latency_ms >= 0
    assert record.failure_reason
    assert "ProviderUnavailableError" in record.failure_reason


@pytest.mark.asyncio
async def test_chat_for_task_missing_usage_fields_logs_none(
    monkeypatch, caplog
):
    """If provider returns usage without prompt/completion keys, log None."""
    provider = _DummyProvider()

    async def _fake_chat(self, messages, *, model=None):
        return ChatResponse(content="x", usage={}, model=model or "")

    monkeypatch.setattr(
        "app.llm.get_for_task", lambda task_key: (provider, "glm-4-flash")
    )
    monkeypatch.setattr(_DummyProvider, "chat", _fake_chat)

    caplog.set_level(logging.INFO, logger="app.llm")
    await chat_for_task(
        "qa_facet_extraction", [ChatMessage(role="user", content="ping")]
    )

    record = _find_llm_call_record(caplog.records)
    assert record.status == "ok"
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
