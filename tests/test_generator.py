"""Tests for Generator service."""
import uuid

import pytest

from app.providers import ChatResponse
from app.services.generator import Citation, Generator
from app.services.hybrid_retriever import HybridRetrievalResult, RetrievedChunk

_UUID1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
_UUID2 = uuid.UUID("00000000-0000-0000-0000-000000000002")


def test_citation_structure():
    """Test Citation dataclass structure."""
    citation = Citation(chunk_id=_UUID1, source_title="来源", page_range="10-12")
    assert citation.chunk_id == _UUID1
    assert citation.page_range == "10-12"


@pytest.mark.asyncio
async def test_generate_v2_with_confidence():
    """Test generate_v2 returns confidence assessment."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(
                content='{"summary": "要点", "details": "详细", "analogy": null, "confidence": {"level": "high", "reason": "证据充分"}}',
                usage={"total_tokens": 100},
            )

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(
                chunk_id=_UUID1,
                content="测试内容",
                bridge_id=_UUID1,
                bridge_name="赵州桥",
                score=0.9,
            ),
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )
    result = await generator.generate_v2("测试问题", evidence)

    assert result.summary == "要点"
    assert result.details == "详细"
    assert result.confidence.level == "high"
    assert result.confidence.reason == "证据充分"
    assert len(result.citations) == 1
    assert result.citations[0].chunk_id == _UUID1


@pytest.mark.asyncio
async def test_generate_v2_with_analogy():
    """Test generate_v2 includes analogy from similar bridges."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(
                content='{"summary": "要点", "details": "详细", "analogy": "类似于卢沟桥的石墩设计", "confidence": {"level": "medium", "reason": "有类比参考"}}',
                usage={"total_tokens": 100},
            )

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[],
        analogy_chunks=[
            RetrievedChunk(
                chunk_id=_UUID2,
                content="卢沟桥石墩设计",
                bridge_id=_UUID2,
                bridge_name="卢沟桥",
                score=0.8,
            ),
        ],
    )
    result = await generator.generate_v2("桥墩如何设计？", evidence)

    assert result.analogy == "类似于卢沟桥的石墩设计"
    assert result.confidence.level == "medium"


@pytest.mark.asyncio
async def test_generate_v2_parse_error_fallback():
    """Test generate_v2 fallback when JSON parsing fails."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(
                content="这不是有效的JSON格式",
                usage={"total_tokens": 50},
            )

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[],
        analogy_chunks=[],
    )
    result = await generator.generate_v2("问题", evidence)

    # Should fallback gracefully
    assert result.confidence.level == "low"
    assert "无法解析" in result.confidence.reason or "格式错误" in result.confidence.reason


@pytest.mark.asyncio
async def test_generate_streaming_returns_event_list():
    """Test generate_streaming returns structured SSE events."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(
                content='{"key_points": [{"summary": "要点一", "explanation": "解释一", "citations": [1]}, {"summary": "要点二", "explanation": "解释二", "citations": [2]}], "deep_dive": null, "confidence": {"level": "high", "reason": "充分"}}',
                usage={"total_tokens": 200},
            )

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=_UUID1, content="内容一", bridge_id=_UUID1, bridge_name="赵州桥", score=0.9),
            RetrievedChunk(chunk_id=_UUID2, content="内容二", bridge_id=_UUID1, bridge_name="赵州桥", score=0.8),
        ],
        concept_chunks=[],
        analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    assert isinstance(events, list)
    event_types = [e[0] for e in events]
    assert event_types[0] == "outline"
    assert event_types[1] == "detail"
    assert event_types[2] == "detail"
    assert event_types[3] == "sources"

    outline_data = events[0][1]
    assert len(outline_data["key_points"]) == 2
    assert outline_data["key_points"][0]["summary"] == "要点一"

    detail_data = events[1][1]
    assert detail_data["explanation"] == "解释一"


@pytest.mark.asyncio
async def test_generate_streaming_fallback_on_bad_json():
    """Test generate_streaming handles malformed LLM output."""

    class MockProvider:
        async def chat(self, messages):
            return ChatResponse(content="这不是JSON", usage={"total_tokens": 50})

    generator = Generator(provider=MockProvider())
    evidence = HybridRetrievalResult(
        anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    assert isinstance(events, list)
    assert len(events) >= 1
    event_types = [e[0] for e in events]
    assert "outline" in event_types or "error" in event_types
