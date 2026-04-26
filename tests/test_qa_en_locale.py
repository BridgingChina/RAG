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

    async def chat_stream(self, messages, *, model=None):  # pragma: no cover — not exercised
        if False:
            yield ""

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


def _run_flow(
    *,
    responses,
    zh_chunks,
    en_chunks,
    question="Zhaozhou Bridge arch",
    monkeypatch=None,
    stream_tokens: list[str] | None = None,
    stream_exc: Exception | None = None,
):
    """Drive the en-qa flow with a single shared ``_ChatStub`` servicing both
    the translation service and the generator fallback.

    Task 9: ``_run_en_qa_flow`` is now an async generator. We collect every
    yielded ``(event_type, payload)`` tuple, peel off the trailing
    ``done_meta`` sentinel, and return a tuple shaped like the legacy
    ``(events, degraded, reason)`` so existing assertions still apply.

    ``stream_tokens`` / ``stream_exc`` control the streamed answer path
    (Step 3): ``stream_tokens`` is the list of markdown tokens
    ``translate_answer_stream`` should yield; ``stream_exc`` short-circuits the
    stream by raising and exercising the legacy
    ``translate_answer_with_evidence`` fallback (which then consumes the next
    queued ``responses`` entry).
    """
    stub = _ChatStub(responses)

    if monkeypatch is not None:
        monkeypatch.setattr(svc, "chat_for_task", stub)
        monkeypatch.setattr(generator_module, "chat_for_task", stub)
    else:
        # Fallback for tests that don't accept monkeypatch — swap directly.
        import pytest as _pytest  # local import
        mp = _pytest.MonkeyPatch()
        mp.setattr(svc, "chat_for_task", stub)
        mp.setattr(generator_module, "chat_for_task", stub)

    # Stub translate_answer_stream: yield tokens or raise. Default is a no-op
    # stream that immediately raises ParseDegradedError on flush (no '## '
    # heading) — tests that don't pass stream_tokens / stream_exc expect to
    # exercise the legacy fallback path (translate_answer_with_evidence
    # pops the next response from the shared stub).
    if stream_exc is not None:
        async def _stream_iter(*_args, **_kwargs):
            raise stream_exc
            if False:  # pragma: no cover — make this an async generator
                yield ""
    else:
        tokens = list(stream_tokens or [])

        async def _stream_iter(*_args, **_kwargs):
            for tok in tokens:
                yield tok

    if monkeypatch is not None:
        monkeypatch.setattr(qa_module, "translate_answer_stream", _stream_iter)

    provider = _FakeProvider()
    retriever = _FakeRetriever(zh_chunks, en_chunks)
    db = MagicMock()

    # Reset the module-level query cache so ordering is deterministic.
    svc._query_translation_cache.clear()

    background_tasks = MagicMock()
    background_tasks.add_task = MagicMock()

    async def _drain():
        events: list[tuple[str, dict]] = []
        degraded = False
        reason: str | None = None
        async for evt_type, payload in qa_module._run_en_qa_flow(
            db=db,
            body=_make_body(question),
            retriever=retriever,
            provider=provider,
            background_tasks=background_tasks,
        ):
            if evt_type == "done_meta":
                degraded = payload["degraded"]
                reason = payload["reason"]
                continue
            events.append((evt_type, payload))
        return events, degraded, reason

    return asyncio.run(_drain()), stub, background_tasks


def test_en_qa_flow_emits_sources_with_text_en_and_not_degraded(monkeypatch):
    zh_chunks = [_make_retrieved_chunk()]
    en_chunks = []
    chunk_id = zh_chunks[0].chunk_id

    # Task 9: streaming path — translate_answer_stream yields markdown tokens
    # that MarkdownStreamParser can parse into outline + detail events.
    # Per-chunk English summaries are produced asynchronously after the stream
    # completes, so on the first request ``text_en`` will be empty (cache miss
    # is the expected steady state for a fresh request).
    stream_md = (
        "# 要点\n"
        "- Zhaozhou Bridge is a Sui-era stone arch bridge. [1]\n"
        "\n"
        "## Sui-era stone arch bridge\n"
        "Zhaozhou Bridge is a Sui-era stone arch bridge built circa 595 CE. [1]\n"
    )
    # Only the query-translate response is consumed via chat_for_task; the
    # answer comes from the stub stream below.
    responses = ["赵州桥的拱结构"]

    (events, degraded, reason), _stub, background_tasks = _run_flow(
        responses=responses, zh_chunks=zh_chunks, en_chunks=en_chunks,
        monkeypatch=monkeypatch,
        stream_tokens=[stream_md],
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
    # Task 9: streaming path emits empty text_en — summaries land via the
    # background task on a subsequent request.
    assert src["text_en"] == ""
    # text_zh preview is preserved for the "Show original Chinese" UI.
    assert "赵州桥" in src["text_zh"]
    # Background extract_evidence_summaries_async scheduled.
    assert background_tasks.add_task.called


def test_en_qa_flow_degrades_on_translate_failure(monkeypatch):
    zh_chunks = [_make_retrieved_chunk()]
    en_chunks = []

    # Task 9: translate_query succeeds, then translate_answer_stream raises.
    # The flow falls back to legacy translate_answer_with_evidence, which
    # consumes the next response from the shared stub — this one is not
    # valid JSON, so the legacy path's degraded=True branch sets the answer
    # to fallback content. We then check the flow surfaces the legacy
    # done_meta reason.
    legacy_response = json.dumps({
        "answer": "Stone arch bridge.",
        "evidence_summaries": [],
    })
    responses = ["赵州桥", legacy_response]
    (events, degraded, reason), _stub, _bg = _run_flow(
        responses=responses, zh_chunks=zh_chunks, en_chunks=en_chunks,
        monkeypatch=monkeypatch,
        stream_exc=RuntimeError("simulated stream failure"),
    )

    # Streaming failed → legacy fallback succeeded → done_meta reports the
    # legacy-fallback degradation marker.
    assert degraded is True
    assert reason == "translate_answer_failed_legacy"
    # Outline + detail + sources should still be emitted on the legacy path.
    types = [t for t, _ in events]
    assert "outline" in types
    assert "detail" in types
    assert "sources" in types


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
    stream_md = (
        "# 要点\n"
        "- Sui-era stone arch. [1]\n"
        "\n"
        "## Sui-era stone arch\n"
        "Zhaozhou Bridge. [1]\n"
    )
    responses = ["赵州桥"]

    with caplog.at_level(logging.INFO, logger="app.api.public.v1.qa"):
        _run_flow(responses=responses, zh_chunks=zh_chunks, en_chunks=[],
                  monkeypatch=monkeypatch, stream_tokens=[stream_md])

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
