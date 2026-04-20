"""Unit tests for the translate-around English QA flow (i18n Phase 4).

Exercises the ``_run_en_qa_flow`` helper directly rather than driving the full
SSE stream, so the test only needs to stub the retriever + translation service,
not a live DB or LLM provider.
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
from app.services import translation_service as svc
from app.services.hybrid_retriever import (
    HybridRetrievalResult,
    RetrievedChunk,
)


@dataclass
class _FakeProvider(LLMProvider):
    default_content: str = ""
    responses: list[str] = field(default_factory=list)
    calls: list = field(default_factory=list)
    chat_model: str | None = None

    async def embed(self, texts):
        return [[0.0] * 8 for _ in texts]

    async def chat(self, messages):
        self.calls.append(messages)
        return ChatResponse(
            content=self.responses.pop(0) if self.responses else self.default_content,
            usage={},
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


def _run_flow(*, responses, zh_chunks, en_chunks, question="Zhaozhou Bridge arch"):
    provider = _FakeProvider(responses=list(responses))
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
    )), provider, background_tasks


def test_en_qa_flow_emits_sources_with_text_en_and_not_degraded():
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

    (events, degraded, reason), provider, background_tasks = _run_flow(
        responses=responses, zh_chunks=zh_chunks, en_chunks=en_chunks,
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


def test_en_qa_flow_degrades_on_translate_failure():
    zh_chunks = [_make_retrieved_chunk()]
    en_chunks = []

    # translate_query succeeds; answer generation returns non-JSON.
    responses = ["赵州桥", "absolutely not json"]
    (events, degraded, reason), _provider, _bg = _run_flow(
        responses=responses, zh_chunks=zh_chunks, en_chunks=en_chunks,
    )

    # degraded falls back to Chinese answer via Generator — the flow returns
    # degraded=True with reason="translate_answer_failed".
    assert degraded is True
    assert reason == "translate_answer_failed"


def test_en_qa_flow_degrades_on_no_evidence():
    # Neither channel returns anything.
    responses = ["赵州桥"]  # Only the query translation call.
    (events, degraded, reason), _provider, _bg = _run_flow(
        responses=responses, zh_chunks=[], en_chunks=[],
    )
    assert degraded is True
    assert reason == "no_evidence"
    # An error event must be emitted to the client.
    assert any(t == "error" for t, _ in events)


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
