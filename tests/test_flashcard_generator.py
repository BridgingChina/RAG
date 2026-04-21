"""Tests for FlashcardBatchGenerator service — Phase C routed via chat_for_task."""
import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.providers import ChatResponse
from app.services import flashcard_generator as fc_module
from app.services.flashcard_generator import FlashcardBatchGenerator


def _patch_chat(monkeypatch, content: str) -> list:
    """Install a recorder and return its call log. Tests use the log to
    assert prompt fragments (e.g. 'no identification cards')."""
    calls: list = []

    async def _fake_chat_for_task(task_key, messages):
        calls.append({"task_key": task_key, "messages": messages})
        return ChatResponse(content=content, usage={}, model="stub-model")

    monkeypatch.setattr(fc_module, "chat_for_task", _fake_chat_for_task)
    return calls


def _make_kp(name="拱桥结构", kp_id=None):
    kp = MagicMock()
    kp.id = kp_id or uuid.uuid4()
    kp.name = name
    kp.taxonomy_node_id = uuid.uuid4()
    return kp


def _make_key_point(summary="拱圈承重", explanation="以拱圈为主要承重构件", order_index=0):
    kpkp = MagicMock()
    kpkp.summary = summary
    kpkp.explanation = explanation
    kpkp.order_index = order_index
    return kpkp


def _make_bridge(name="赵州桥", bridge_id=None):
    b = MagicMock()
    b.id = bridge_id or uuid.uuid4()
    b.name = name
    return b


def _make_kp_bridge(bridge_id):
    kpb = MagicMock()
    kpb.bridge_id = bridge_id
    return kpb


def _mock_db_queries(db, kp, key_points, bridges, kp_bridges):
    """Set up chained query mocks for the generator."""
    def _query_side_effect(model):
        q = MagicMock()
        from app.models import (
            Bridge,
            Flashcard,
            KnowledgePoint,
            KnowledgePointBridge,
            KnowledgePointKeyPoint,
        )

        if model is KnowledgePoint:
            q.filter.return_value.first.return_value = kp
        elif model is KnowledgePointKeyPoint:
            q.filter.return_value.order_by.return_value.all.return_value = key_points
        elif model is KnowledgePointBridge:
            q.filter.return_value.all.return_value = kp_bridges
        elif model is Bridge:
            q.filter.return_value.all.return_value = bridges
        elif model is Flashcard:
            q.filter.return_value.delete.return_value = 0
        return q

    db.query.side_effect = _query_side_effect


@pytest.mark.asyncio
async def test_generate_for_kp_creates_cards(monkeypatch):
    """Test that generate_for_kp creates flashcards from LLM response."""
    kp_id = uuid.uuid4()
    bridge = _make_bridge("赵州桥")
    kp = _make_kp("拱桥结构", kp_id=kp_id)
    key_points = [_make_key_point("拱圈承重", "以拱圈为主要承重构件")]
    kp_bridges = [_make_kp_bridge(bridge.id)]

    db = MagicMock()
    _mock_db_queries(db, kp, key_points, [bridge], kp_bridges)

    llm_content = json.dumps({
        "cards": [
            {
                "card_type": "concept",
                "front_title": "什么是拱桥？",
                "front_hint": "古代桥梁结构",
                "back_answer": "以拱圈为主要承重构件的桥梁",
                "back_key_features": ["拱圈承重", "轴向压力"],
                "example_bridge_name": None,
            },
            {
                "card_type": "identification",
                "front_title": "哪座桥是敞肩拱的典型代表？",
                "front_hint": "隋代，河北",
                "back_answer": "赵州桥",
                "back_key_features": ["敞肩拱"],
                "example_bridge_name": "赵州桥",
            },
        ]
    })
    _patch_chat(monkeypatch, llm_content)

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id)

    assert len(cards) == 2
    assert cards[0].card_type == "concept"
    assert cards[0].front_title == "什么是拱桥？"
    assert cards[0].back_example_bridge_id is None
    assert cards[1].card_type == "identification"
    assert cards[1].back_example_bridge_id == bridge.id
    assert db.add.call_count == 2


@pytest.mark.asyncio
async def test_generate_skips_identification_when_no_bridges(monkeypatch):
    """Test that prompt instructs no identification cards when no bridges."""
    kp_id = uuid.uuid4()
    kp = _make_kp("梁桥结构", kp_id=kp_id)
    key_points = [_make_key_point("简支梁", "最简单的桥梁结构")]

    db = MagicMock()
    _mock_db_queries(db, kp, key_points, bridges=[], kp_bridges=[])

    llm_content = json.dumps({
        "cards": [
            {
                "card_type": "concept",
                "front_title": "什么是梁桥？",
                "front_hint": None,
                "back_answer": "以梁为主要承重构件的桥梁",
                "back_key_features": ["简支梁"],
                "example_bridge_name": None,
            },
        ]
    })
    calls = _patch_chat(monkeypatch, llm_content)

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id)

    assert len(cards) == 1
    assert cards[0].card_type == "concept"
    assert cards[0].back_example_bridge_id is None

    # Verify prompt mentions no identification cards
    assert calls, "expected at least one chat_for_task call"
    prompt_arg = calls[0]["messages"][0].content
    assert "不要生成 identification 卡" in prompt_arg


@pytest.mark.asyncio
async def test_parse_llm_response_handles_malformed_json(monkeypatch):
    """Test that malformed JSON from LLM raises an exception."""
    kp_id = uuid.uuid4()
    kp = _make_kp("拱桥结构", kp_id=kp_id)

    db = MagicMock()
    _mock_db_queries(db, kp, key_points=[], bridges=[], kp_bridges=[])

    _patch_chat(monkeypatch, "This is not valid JSON at all")

    generator = FlashcardBatchGenerator()
    with pytest.raises(json.JSONDecodeError):
        await generator.generate_for_kp(db, kp_id)


@pytest.mark.asyncio
async def test_parse_llm_response_handles_markdown_fences(monkeypatch):
    """Test that markdown-fenced JSON is parsed correctly."""
    kp_id = uuid.uuid4()
    kp = _make_kp("拱桥结构", kp_id=kp_id)

    db = MagicMock()
    _mock_db_queries(db, kp, key_points=[], bridges=[], kp_bridges=[])

    _patch_chat(
        monkeypatch,
        '```json\n{"cards": [{"card_type": "concept", "front_title": "测试", "back_answer": "答案"}]}\n```',
    )

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id)

    assert len(cards) == 1
    assert cards[0].front_title == "测试"


@pytest.mark.asyncio
async def test_bridge_name_matching_case_insensitive(monkeypatch):
    """Test that bridge name matching is case-insensitive."""
    kp_id = uuid.uuid4()
    bridge = _make_bridge("赵州桥")
    kp = _make_kp("拱桥结构", kp_id=kp_id)
    kp_bridges = [_make_kp_bridge(bridge.id)]

    db = MagicMock()
    _mock_db_queries(db, kp, key_points=[], bridges=[bridge], kp_bridges=kp_bridges)

    _patch_chat(
        monkeypatch,
        json.dumps({
            "cards": [
                {
                    "card_type": "identification",
                    "front_title": "测试",
                    "back_answer": "赵州桥",
                    "example_bridge_name": "赵州桥",
                },
            ]
        }),
    )

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id)

    assert cards[0].back_example_bridge_id == bridge.id
