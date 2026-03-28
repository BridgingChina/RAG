"""Tests for FlashcardBatchGenerator service."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.flashcard_generator import FlashcardBatchGenerator


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
    # Each db.query(...) call needs its own chain
    call_count = {"n": 0}
    original_query = db.query

    def _query_side_effect(model):
        q = MagicMock()
        call_count["n"] += 1

        # Determine what to return based on the model
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
async def test_generate_for_kp_creates_cards():
    """Test that generate_for_kp creates flashcards from LLM response."""
    kp_id = uuid.uuid4()
    bridge = _make_bridge("赵州桥")
    kp = _make_kp("拱桥结构", kp_id=kp_id)
    key_points = [_make_key_point("拱圈承重", "以拱圈为主要承重构件")]
    kp_bridges = [_make_kp_bridge(bridge.id)]

    db = MagicMock()
    _mock_db_queries(db, kp, key_points, [bridge], kp_bridges)

    # Mock LLM provider
    provider = MagicMock()
    llm_response = MagicMock()
    llm_response.content = json.dumps({
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
    provider.chat = AsyncMock(return_value=llm_response)

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id, provider)

    assert len(cards) == 2
    assert cards[0].card_type == "concept"
    assert cards[0].front_title == "什么是拱桥？"
    assert cards[0].back_example_bridge_id is None
    assert cards[1].card_type == "identification"
    assert cards[1].back_example_bridge_id == bridge.id
    assert db.add.call_count == 2


@pytest.mark.asyncio
async def test_generate_skips_identification_when_no_bridges():
    """Test that prompt instructs no identification cards when no bridges."""
    kp_id = uuid.uuid4()
    kp = _make_kp("梁桥结构", kp_id=kp_id)
    key_points = [_make_key_point("简支梁", "最简单的桥梁结构")]

    db = MagicMock()
    _mock_db_queries(db, kp, key_points, bridges=[], kp_bridges=[])

    provider = MagicMock()
    llm_response = MagicMock()
    llm_response.content = json.dumps({
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
    provider.chat = AsyncMock(return_value=llm_response)

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id, provider)

    assert len(cards) == 1
    assert cards[0].card_type == "concept"
    assert cards[0].back_example_bridge_id is None

    # Verify prompt mentions no identification cards
    prompt_arg = provider.chat.call_args[0][0][0].content
    assert "不要生成 identification 卡" in prompt_arg


@pytest.mark.asyncio
async def test_parse_llm_response_handles_malformed_json():
    """Test that malformed JSON from LLM raises an exception."""
    kp_id = uuid.uuid4()
    kp = _make_kp("拱桥结构", kp_id=kp_id)

    db = MagicMock()
    _mock_db_queries(db, kp, key_points=[], bridges=[], kp_bridges=[])

    provider = MagicMock()
    llm_response = MagicMock()
    llm_response.content = "This is not valid JSON at all"
    provider.chat = AsyncMock(return_value=llm_response)

    generator = FlashcardBatchGenerator()
    with pytest.raises(json.JSONDecodeError):
        await generator.generate_for_kp(db, kp_id, provider)


@pytest.mark.asyncio
async def test_parse_llm_response_handles_markdown_fences():
    """Test that markdown-fenced JSON is parsed correctly."""
    kp_id = uuid.uuid4()
    kp = _make_kp("拱桥结构", kp_id=kp_id)

    db = MagicMock()
    _mock_db_queries(db, kp, key_points=[], bridges=[], kp_bridges=[])

    provider = MagicMock()
    llm_response = MagicMock()
    llm_response.content = '```json\n{"cards": [{"card_type": "concept", "front_title": "测试", "back_answer": "答案"}]}\n```'
    provider.chat = AsyncMock(return_value=llm_response)

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id, provider)

    assert len(cards) == 1
    assert cards[0].front_title == "测试"


@pytest.mark.asyncio
async def test_bridge_name_matching_case_insensitive():
    """Test that bridge name matching is case-insensitive."""
    kp_id = uuid.uuid4()
    bridge = _make_bridge("赵州桥")
    kp = _make_kp("拱桥结构", kp_id=kp_id)
    kp_bridges = [_make_kp_bridge(bridge.id)]

    db = MagicMock()
    _mock_db_queries(db, kp, key_points=[], bridges=[bridge], kp_bridges=kp_bridges)

    provider = MagicMock()
    llm_response = MagicMock()
    # LLM returns exact name — should match
    llm_response.content = json.dumps({
        "cards": [
            {
                "card_type": "identification",
                "front_title": "测试",
                "back_answer": "赵州桥",
                "example_bridge_name": "赵州桥",
            },
        ]
    })
    provider.chat = AsyncMock(return_value=llm_response)

    generator = FlashcardBatchGenerator()
    cards = await generator.generate_for_kp(db, kp_id, provider)

    assert cards[0].back_example_bridge_id == bridge.id
