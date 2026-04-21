"""Unit tests for the translate-around English QA flow (i18n Phase 4).

Phase C: the flow's LLM calls (translate_query_zh / translate_answer_with_evidence
/ Generator fallback) are all routed via :func:`chat_for_task`. Tests monkey-
patch that symbol on the relevant service modules and feed canned responses
through a shared queue, so the flow executes end-to-end without live DB/LLM.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.api.public.v1 import qa as qa_module
from app.providers.base import ChatResponse, LLMProvider
from app.services import generator as generator_module
from app.services import translation_service as svc
from app.services.hybrid_retriever import (
    HybridRetrievalResult,
    RetrievedChunk,
)


@dataclass
class _FakeProvider(LLMProvider):
    """Stand-in for ZhipuProvider — the en-qa flow only calls ``embed()`` on
    this object now (for the English保底 retrieval branch inside
    ``retriever.search_by_english_embedding``)."""

    default_content: str = ""
    responses: list[str] = field(default_factory=list)
    calls: list = field(default_factory=list)
    chat_model: str | None = None

    async def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

    async def chat(self, messages):
        # Should not be called in Phase C — translation goes through
        # chat_for_task, not the provider directly.
        self.calls.append(messages)
        return ChatResponse(
            content=self.responses.pop(0) if self.responses else self.default_content,
            usage={},
        )

    async def list_models(self):
        return []


class _ChatStub:
    """Shared async stub that dispenses responses in order. Installed on
    every module that calls ``chat_for_task`` so a single queue drives the
    whole flow (query-translate, then answer-generate)."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list = []

    async def __call__(self, task_key, messages):
        self.calls.append({"task_key": task_key, "messages": messages})
        if not self._responses:
            raise AssertionError(
                f"ChatStub out of responses (task_key={task_key}); "
                f"test queued too few."
            )
        return ChatResponse(
            content=self._responses.pop(0), usage={}, model="stub-model"
        )


def _make_retrieved_chunk(content: str = "赵州桥是石拱桥") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid4(),
        content=content,
        bridge_id=uuid4(),
        bridge_name="赵州桥",
        score=0.9,
    )


class _FakeRetriever:
    def __init__(self, zh_chunks, en_chunks):
        self._zh_chunks = zh_chunks
        self._en_chunks = en_chunks

    async def retrieve(self, db, query, **kwargs):
        return HybridRetrievalResult(
            anchor_chunks=list(self._zh_chunks),
            concept_chunks=[],
            analogy_chunks=[],
        )

    async def search_by_english_embedding(self, db, query_en, *, top_k=10):
        return list(self._en_chunks)


def _make_body(question: str):
    return SimpleNamespace(question=question, context=None)


def _run_flow(*, responses, zh_chunks, en_chunks, question="Zhaozhou Bridge arch", monkeypatch=None):
    """Drive the en-qa flow with a single shared ``_ChatStub`` servicing both
    the translation service and the generator fallback."""
    stub = _ChatStub(responses)

    if monkeypatch is not None:
        monkeypatch.setattr(svc, "chat_for_task", stub)
        monkeypatch.setattr(generator_module, "chat_for_task", stub)
    else:
        # Fallback for tests that don't accept monkeypatch — swap directly.
        # pytest.MonkeyPatch works similarly, but we avoid importing it here
        # to keep the test style consistent with the rest of the suite.
        import pytest as _pytest  # local import
        mp = _pytest.MonkeyPatch()
        mp.setattr(svc, "chat_for_task", stub)
        mp.setattr(generator_module, "chat_for_task", stub)
        # Caller is responsible for undo — test fixtures usually handle this,
        # but since these helpers run outside a fixture we leak the patch for
        # the test's lifetime (process-local, no cross-test bleed because
        # each call installs fresh).

    provider = _FakeProvider()
    retriever = _FakeRetriever(zh_chunks, en_chunks)
    db = MagicMock()

    # DB lookup used by the en-flow's cache-hit check — make every chunk a miss.
    scalar_mock = MagicMock(return_value=None)
    db.query.return_value.filter.return_value.scalar = scalar_mock

    # Reset the module-level query cache so ordering is deterministic.
    svc._query_translation_cache.clear()

    background_tasks = MagicMock()
    background_tasks.add_task = MagicMock()

    return asyncio.run(qa_module._run_en_qa_flow(
        db=db,
        body=_make_body(question),
        retriever=retriever,
        provider=provider,
        background_tasks=background_tasks,
    )), stub, background_tasks


def test_en_qa_flow_emits_sources_with_text_en_and_not_degraded(monkeypatch):
    zh_chunks = [_make_retrieved_chunk()]
    en_chunks = []
    chunk_id = zh_chunks[0].chunk_id

    answer_json = json.dumps({
        "answer": "Zhaozhou Bridge is a Sui-era stone arch bridge.",
        "evidence_summaries": [
            {"chunk_id": str(chunk_id), "text_en": "Sui-era arch bridge summary."},
        ],
    })
    # Query-translate first, then answer-generate.
    responses = ["赵州桥的拱结构", answer_json]

    (events, degraded, reason), stub, background_tasks = _run_flow(
        responses=responses, zh_chunks=zh_chunks, en_chunks=en_chunks,
        monkeypatch=monkeypatch,
    )
    assert degraded is False
    assert reason is None

    event_types = [t for t, _ in events]
    assert "translated_query" in event_types
    assert "outline" in event_types
    assert "detail" in event_types
    assert "sources" in event_types

    sources_event = next(data for t, data in events if t == "sources")
    src = sources_event["sources"][0]
    assert src["chunk_id"] == str(chunk_id)
    assert "Sui-era arch bridge summary" in src["text_en"]
    # text_zh preview is preserved for the "Show original Chinese" UI.
    assert "赵州桥" in src["text_zh"]
    # Background cache write scheduled.
    assert background_tasks.add_task.called


def test_en_qa_flow_degrades_on_translate_failure(monkeypatch):
    zh_chunks = [_make_retrieved_chunk()]
    en_chunks = []

    # translate_query succeeds; answer generation returns non-JSON. After
    # degradation, the flow falls back to Generator.generate_streaming which
    # makes its OWN chat_for_task call — queue a third response.
    generator_fallback = json.dumps({
        "key_points": [{"summary": "cn", "explanation": "cn", "citations": []}],
        "deep_dive": None,
        "confidence": {"level": "low", "reason": "fallback"},
    })
    responses = ["赵州桥", "absolutely not json", generator_fallback]
    (events, degraded, reason), _stub, _bg = _run_flow(
        responses=responses, zh_chunks=zh_chunks, en_chunks=en_chunks,
        monkeypatch=monkeypatch,
    )

    # degraded falls back to Chinese answer via Generator — the flow returns
    # degraded=True with reason="translate_answer_failed".
    assert degraded is True
    assert reason == "translate_answer_failed"


def test_en_qa_flow_degrades_on_no_evidence(monkeypatch):
    # Neither channel returns anything.
    responses = ["赵州桥"]  # Only the query translation call.
    (events, degraded, reason), _stub, _bg = _run_flow(
        responses=responses, zh_chunks=[], en_chunks=[],
        monkeypatch=monkeypatch,
    )
    assert degraded is True
    assert reason == "no_evidence"
    # An error event must be emitted to the client.
    assert any(t == "error" for t, _ in events)


def test_settings_i18n_enabled_defaults_to_true():
    """Phase 5 rollback flag is on by default so production keeps the
    translate-around flow until an env var flips it."""
    from app.core.config import Settings

    assert Settings().i18n_enabled is True


def test_en_qa_flow_emits_structured_metrics_log(caplog, monkeypatch):
    """Phase 4.F.1: success-path flow emits a `qa.en_metrics` log line with
    stage timings + cache hit rate, for offline P50/P95 aggregation."""
    import logging

    zh_chunks = [_make_retrieved_chunk()]
    chunk_id = zh_chunks[0].chunk_id
    answer_json = json.dumps({
        "answer": "Zhaozhou Bridge is a Sui-era stone arch bridge.",
        "evidence_summaries": [
            {"chunk_id": str(chunk_id), "text_en": "Sui-era arch."},
        ],
    })
    responses = ["赵州桥", answer_json]

    with caplog.at_level(logging.INFO, logger="app.api.public.v1.qa"):
        _run_flow(responses=responses, zh_chunks=zh_chunks, en_chunks=[],
                  monkeypatch=monkeypatch)

    metric_records = [r for r in caplog.records if "qa.en_metrics" in r.getMessage()]
    assert metric_records, "expected a qa.en_metrics log record on success"
    msg = metric_records[-1].getMessage()
    # stage timings + cache counters all present
    for key in ("query_translate_ms", "retrieval_ms", "generate_ms",
                "total_ms", "cache_total", "cache_hits"):
        assert key in msg, f"missing metric {key!r} in log message: {msg}"


def test_rrf_merge_retrieved_prefers_zh_weighted_results():
    chunk_a = _make_retrieved_chunk("chunk-A")
    chunk_b = _make_retrieved_chunk("chunk-B")
    merged = qa_module._rrf_merge_retrieved(
        zh_chunks=[chunk_a, chunk_b],
        en_chunks=[chunk_b],
        zh_weight=0.7,
        en_weight=0.3,
        limit=5,
    )
    # Both chunks retained, in descending score order.
    assert {c.chunk_id for c in merged} == {chunk_a.chunk_id, chunk_b.chunk_id}
    # chunk_b shows up in both lists, so it should outscore chunk_a.
    assert merged[0].chunk_id == chunk_b.chunk_id
