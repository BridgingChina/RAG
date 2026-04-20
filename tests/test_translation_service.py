"""Unit tests for app.services.translation_service (i18n Phases 3 & 4).

Does not require a live database — uses a minimal in-memory fake ``Session``
for state-machine tests and a simple recording fake ``LLMProvider`` for
LLM-facing paths. Async tests use ``asyncio.run()`` directly to avoid needing
``pytest-asyncio`` mode changes.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.glossary import GlossaryTerm
from app.models.translation_review import (
    TRANSLATION_STATUS_AI_GENERATED,
    TRANSLATION_STATUS_HUMAN_REVIEWED,
    TRANSLATION_STATUS_PENDING_AI,
    TRANSLATION_STATUS_REJECTED,
    TranslationReview,
)
from app.providers.base import ChatResponse, LLMProvider
from app.services import translation_service as svc


# --- Fake LLM provider ----------------------------------------------------


@dataclass
class _FakeProvider(LLMProvider):
    """Records every chat() call; returns the next queued response (or a
    reusable default)."""

    default_content: str = ""
    responses: list[str] = field(default_factory=list)
    calls: list = field(default_factory=list)
    chat_model: str | None = None

    async def embed(self, texts):  # pragma: no cover — not used by translation_service
        return [[0.0] * 4 for _ in texts]

    async def chat(self, messages):
        self.calls.append({
            "model": self.chat_model,
            "content": "\n".join(m.content for m in messages),
        })
        if self.responses:
            reply = self.responses.pop(0)
        else:
            reply = self.default_content
        return ChatResponse(content=reply, usage={})


# --- translate_query_zh ---------------------------------------------------


def test_translate_query_zh_basic_cache_hit():
    """Second call with the same query must NOT hit the LLM."""
    provider = _FakeProvider(default_content="赵州桥拱的结构")
    cache = svc._LRUCache(maxsize=16)
    result_a = asyncio.run(svc.translate_query_zh(
        "Arch structure of Zhaozhou Bridge",
        zhipu_client=provider, glossary=[], cache=cache,
    ))
    result_b = asyncio.run(svc.translate_query_zh(
        "Arch structure of Zhaozhou Bridge",
        zhipu_client=provider, glossary=[], cache=cache,
    ))
    assert result_a == "赵州桥拱的结构"
    assert result_b == "赵州桥拱的结构"
    # Only one LLM call.
    assert len(provider.calls) == 1


def test_translate_query_zh_injects_glossary_terms():
    provider = _FakeProvider(default_content="赵州桥的券拱结构")
    glossary = [
        GlossaryTerm(zh="赵州桥", en="Zhaozhou Bridge", context="general"),
        GlossaryTerm(zh="券拱", en="voussoir arch", context="structural"),
    ]
    asyncio.run(svc.translate_query_zh(
        "What is the voussoir arch of Zhaozhou Bridge?",
        zhipu_client=provider, glossary=glossary, cache=svc._LRUCache(maxsize=1),
    ))
    prompt = provider.calls[0]["content"]
    # Glossary terms land in the prompt verbatim.
    assert "赵州桥" in prompt
    assert "voussoir arch" in prompt
    # And the cheap model is selected.
    assert provider.calls[0]["model"] == svc.CHEAP_TRANSLATION_MODEL


def test_translate_query_zh_strips_llm_wrapping():
    """Markdown fences / surrounding quotes should be scrubbed off."""
    provider = _FakeProvider(default_content='```\n"赵州桥的结构"\n```')
    result = asyncio.run(svc.translate_query_zh(
        "Zhaozhou Bridge structure",
        zhipu_client=provider, glossary=[], cache=svc._LRUCache(maxsize=1),
    ))
    assert result == "赵州桥的结构"


# --- translate_answer_with_evidence --------------------------------------


def test_translate_answer_with_evidence_happy_path():
    provider = _FakeProvider()
    provider.responses.append(json.dumps({
        "answer": "Zhaozhou Bridge is a Sui-era stone arch bridge...",
        "evidence_summaries": [
            {"chunk_id": str(uuid4()), "text_en": "Sui-era arch bridge"},
            {"chunk_id": str(uuid4()), "text_en": "Stone voussoir construction"},
        ],
    }))
    chunk_a = SimpleNamespace(chunk_id=uuid4(), content="赵州桥是石拱桥", bridge_name="赵州桥")
    chunk_b = SimpleNamespace(chunk_id=uuid4(), content="隋朝建造", bridge_name="赵州桥")

    result = asyncio.run(svc.translate_answer_with_evidence(
        "Tell me about Zhaozhou Bridge",
        [chunk_a, chunk_b],
        zhipu_client=provider,
        glossary=[],
    ))

    assert result["degraded"] is False
    assert "Zhaozhou Bridge" in result["answer"]
    assert len(result["evidence_summaries"]) == 2
    assert all("chunk_id" in s and "text_en" in s for s in result["evidence_summaries"])
    # Quality model is used for answer generation.
    assert provider.calls[0]["model"] == svc.QUALITY_ANSWER_MODEL


def test_translate_answer_with_evidence_degrades_on_bad_json():
    provider = _FakeProvider(default_content="This is not JSON at all.")
    chunk_a = SimpleNamespace(chunk_id=uuid4(), content="内容", bridge_name=None)
    result = asyncio.run(svc.translate_answer_with_evidence(
        "question",
        [chunk_a],
        zhipu_client=provider,
        glossary=[],
    ))
    assert result["degraded"] is True
    assert result["answer"] == ""
    assert result["evidence_summaries"] == []


def test_translate_answer_with_evidence_empty_evidence_returns_degraded():
    provider = _FakeProvider(default_content='{"answer": "x", "evidence_summaries": []}')
    result = asyncio.run(svc.translate_answer_with_evidence(
        "question",
        [],
        zhipu_client=provider,
        glossary=[],
    ))
    assert result["degraded"] is True
    # No LLM call was made.
    assert provider.calls == []


# --- generate_for_row and approve_review state machine --------------------


def _make_mock_session_with_reviews() -> MagicMock:
    """Build a MagicMock Session whose query/filter chain returns from an
    in-memory dict. Sufficient for state-machine coverage without pg."""
    store: dict = {}

    session = MagicMock()

    def _add(obj):
        if isinstance(obj, TranslationReview):
            if obj.id is None:
                obj.id = uuid4()
            store[obj.id] = obj

    def _flush():
        return None

    def _query(cls):
        query_mock = MagicMock()
        # filter().one_or_none() — lookup by review_id, or (table, row, field)
        def _filter(*args):
            filt = MagicMock()
            # Build a matcher over criteria
            def _matches(review: TranslationReview) -> bool:
                for arg in args:
                    # Each arg is a BinaryExpression. Compare via string for test simplicity.
                    # The service passes TranslationReview.id == x etc.
                    left_col = getattr(arg.left, "name", None) or str(arg.left)
                    right_val = getattr(arg.right, "value", arg.right)
                    if left_col == "id":
                        if review.id != right_val:
                            return False
                    elif left_col == "table_name":
                        if review.table_name != right_val:
                            return False
                    elif left_col == "row_id":
                        if review.row_id != right_val:
                            return False
                    elif left_col == "field_name":
                        if review.field_name != right_val:
                            return False
                return True
            filt.one_or_none.return_value = next(
                (r for r in store.values() if _matches(r)), None
            )
            return filt
        query_mock.filter.side_effect = _filter
        return query_mock

    session.add.side_effect = _add
    session.flush.side_effect = _flush
    session.query.side_effect = _query
    session.execute.return_value = MagicMock()
    session._store = store
    return session


def test_generate_for_row_creates_pending_then_ai_generated():
    session = _make_mock_session_with_reviews()
    provider = _FakeProvider(default_content="Zhaozhou Bridge")
    row_id = uuid4()

    review = asyncio.run(svc.generate_for_row(
        session,
        table_name="bridges",
        row_id=row_id,
        field_name="name_en",
        source_text="赵州桥",
        zhipu_client=provider,
    ))

    assert review.status == TRANSLATION_STATUS_AI_GENERATED
    assert review.ai_translation == "Zhaozhou Bridge"


def test_generate_for_row_is_idempotent_for_human_reviewed():
    session = _make_mock_session_with_reviews()
    existing_id = uuid4()
    existing = TranslationReview(
        id=existing_id,
        table_name="bridges",
        row_id=uuid4(),
        field_name="name_en",
        source_text="赵州桥",
        ai_translation="old",
        reviewed_translation="Zhaozhou Bridge (human)",
        status=TRANSLATION_STATUS_HUMAN_REVIEWED,
    )
    session._store[existing_id] = existing
    provider = _FakeProvider(default_content="SHOULD NOT BE CALLED")

    result = asyncio.run(svc.generate_for_row(
        session,
        table_name="bridges",
        row_id=existing.row_id,
        field_name="name_en",
        source_text="赵州桥",
        zhipu_client=provider,
    ))

    assert result.status == TRANSLATION_STATUS_HUMAN_REVIEWED
    assert provider.calls == []  # No LLM invocation — existing审校 preserved


def test_approve_review_writes_back_to_business_table():
    """approve_review should (1) flip status, (2) set reviewed fields, (3)
    call session.execute with an UPDATE on the business table."""
    session = _make_mock_session_with_reviews()
    review_id = uuid4()
    row_id = uuid4()
    review = TranslationReview(
        id=review_id,
        table_name="bridges",
        row_id=row_id,
        field_name="name_en",
        source_text="赵州桥",
        ai_translation="Zhaozhou Bridge",
        status=TRANSLATION_STATUS_AI_GENERATED,
    )
    session._store[review_id] = review

    result = asyncio.run(svc.approve_review(
        session, review_id=review_id, reviewer_id="admin-123",
    ))

    assert result.status == TRANSLATION_STATUS_HUMAN_REVIEWED
    assert result.reviewed_translation == "Zhaozhou Bridge"
    assert result.reviewed_by == "admin-123"
    assert result.reviewed_at is not None

    # session.execute is called once for the business-table UPDATE.
    assert session.execute.call_count == 1


def test_approve_review_with_edit_uses_provided_text():
    session = _make_mock_session_with_reviews()
    review_id = uuid4()
    review = TranslationReview(
        id=review_id,
        table_name="bridges",
        row_id=uuid4(),
        field_name="name_en",
        source_text="赵州桥",
        ai_translation="Zhaozhou Bridge draft",
        status=TRANSLATION_STATUS_AI_GENERATED,
    )
    session._store[review_id] = review

    result = asyncio.run(svc.approve_review(
        session,
        review_id=review_id,
        reviewer_id="admin-123",
        reviewed_translation="Zhaozhou Bridge (edited)",
    ))

    assert result.reviewed_translation == "Zhaozhou Bridge (edited)"
    assert result.status == TRANSLATION_STATUS_HUMAN_REVIEWED


def test_approve_review_rejects_missing_translation():
    session = _make_mock_session_with_reviews()
    review_id = uuid4()
    # Still pending — ai_translation is None
    review = TranslationReview(
        id=review_id,
        table_name="bridges", row_id=uuid4(), field_name="name_en",
        source_text="赵州桥", ai_translation=None,
        status=TRANSLATION_STATUS_PENDING_AI,
    )
    session._store[review_id] = review

    with pytest.raises(ValueError):
        asyncio.run(svc.approve_review(
            session, review_id=review_id, reviewer_id="admin-123",
        ))


def test_reject_review_flips_status_and_skips_business_write():
    session = _make_mock_session_with_reviews()
    review_id = uuid4()
    review = TranslationReview(
        id=review_id,
        table_name="bridges", row_id=uuid4(), field_name="name_en",
        source_text="赵州桥", ai_translation="draft",
        status=TRANSLATION_STATUS_AI_GENERATED,
    )
    session._store[review_id] = review

    result = svc.reject_review(
        session, review_id=review_id, reviewer_id="admin-123",
    )

    assert result.status == TRANSLATION_STATUS_REJECTED
    assert session.execute.call_count == 0  # No business-table write
