"""Tests for Generator service — Phase C routed via chat_for_task."""
import uuid

import pytest

from app.providers import ChatResponse
from app.services import generator as generator_module
from app.services.generator import Citation, Generator
from app.services.hybrid_retriever import HybridRetrievalResult, RetrievedChunk

_UUID1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
_UUID2 = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _patch_chat(monkeypatch, content: str):
    async def _fake(task_key, messages):
        return ChatResponse(content=content, usage={"total_tokens": 100}, model="stub-model")

    monkeypatch.setattr(generator_module, "chat_for_task", _fake)


def test_citation_structure():
    """Test Citation dataclass structure."""
    citation = Citation(chunk_id=_UUID1, source_title="来源", page_range="10-12")
    assert citation.chunk_id == _UUID1
    assert citation.page_range == "10-12"


@pytest.mark.asyncio
async def test_generate_v2_with_confidence(monkeypatch):
    """Test generate_v2 returns confidence assessment."""
    _patch_chat(
        monkeypatch,
        '{"summary": "要点", "details": "详细", "analogy": null, '
        '"confidence": {"level": "high", "reason": "证据充分"}}',
    )

    generator = Generator()
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
async def test_generate_v2_with_analogy(monkeypatch):
    """Test generate_v2 includes analogy from similar bridges."""
    _patch_chat(
        monkeypatch,
        '{"summary": "要点", "details": "详细", "analogy": "类似于卢沟桥的石墩设计", '
        '"confidence": {"level": "medium", "reason": "有类比参考"}}',
    )

    generator = Generator()
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
async def test_generate_v2_parse_error_fallback(monkeypatch):
    """Test generate_v2 fallback when JSON parsing fails."""
    _patch_chat(monkeypatch, "这不是有效的JSON格式")

    generator = Generator()
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
async def test_generate_streaming_returns_event_list(monkeypatch):
    """Test generate_streaming returns structured SSE events."""
    _patch_chat(
        monkeypatch,
        '{"key_points": [{"summary": "要点一", "explanation": "解释一", "citations": [1]}, '
        '{"summary": "要点二", "explanation": "解释二", "citations": [2]}], '
        '"deep_dive": null, "confidence": {"level": "high", "reason": "充分"}}',
    )

    generator = Generator()
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
async def test_generate_streaming_fallback_on_bad_json(monkeypatch):
    """Test generate_streaming handles malformed LLM output."""
    _patch_chat(monkeypatch, "这不是JSON")

    generator = Generator()
    evidence = HybridRetrievalResult(
        anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    assert isinstance(events, list)
    assert len(events) >= 1
    event_types = [e[0] for e in events]
    assert "outline" in event_types or "error" in event_types


_UUID3 = uuid.UUID("00000000-0000-0000-0000-000000000003")


@pytest.mark.asyncio
async def test_generate_streaming_sources_contiguous_ids(monkeypatch):
    """Sources event has contiguous IDs even when multiple chunks share bridge_name."""
    _patch_chat(
        monkeypatch,
        '{"key_points": [{"summary": "s", "explanation": "e", "citations": [1]}], '
        '"deep_dive": null, "confidence": {"level": "high", "reason": "ok"}}',
    )

    generator = Generator()
    evidence = HybridRetrievalResult(
        anchor_chunks=[
            RetrievedChunk(chunk_id=_UUID1, content="赵州桥内容一", bridge_id=_UUID1, bridge_name="赵州桥", score=0.9),
            RetrievedChunk(chunk_id=_UUID2, content="赵州桥内容二", bridge_id=_UUID1, bridge_name="赵州桥", score=0.8),
        ],
        concept_chunks=[],
        analogy_chunks=[
            RetrievedChunk(chunk_id=_UUID3, content="卢沟桥内容", bridge_id=_UUID3, bridge_name="卢沟桥", score=0.7),
        ],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    sources_event = [e for e in events if e[0] == "sources"]
    assert len(sources_event) == 1
    sources_list = sources_event[0][1]["sources"]
    assert len(sources_list) == 2
    assert sources_list[0]["id"] == 1
    assert sources_list[1]["id"] == 2
    assert sources_list[0]["title"] == "赵州桥"
    assert sources_list[1]["title"] == "卢沟桥"


@pytest.mark.asyncio
async def test_generate_streaming_sources_no_bridge_name(monkeypatch):
    """Chunks with bridge_name='' get fallback name '来源'."""
    _patch_chat(
        monkeypatch,
        '{"key_points": [{"summary": "s", "explanation": "e", "citations": []}], '
        '"deep_dive": null, "confidence": {"level": "low", "reason": "ok"}}',
    )

    generator = Generator()
    evidence = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[
            RetrievedChunk(chunk_id=_UUID1, content="通用内容", bridge_id=None, bridge_name="", score=0.5),
        ],
        analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试", evidence)

    sources_event = [e for e in events if e[0] == "sources"][0]
    sources_list = sources_event[1]["sources"]
    assert len(sources_list) == 1
    assert sources_list[0]["title"] == "来源"


@pytest.mark.asyncio
async def test_generate_streaming_fallback_asserts_specific_behavior(monkeypatch):
    """When LLM returns non-JSON, fallback produces exactly 3 events with expected structure."""
    raw_content = "这不是JSON格式的响应内容"
    _patch_chat(monkeypatch, raw_content)

    generator = Generator()
    evidence = HybridRetrievalResult(
        anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试问题", evidence)

    assert len(events) == 3
    assert events[0][0] == "outline"
    assert events[1][0] == "detail"
    assert events[2][0] == "sources"

    # Outline has exactly 1 key_point with content truncated at 200 chars
    outline_kps = events[0][1]["key_points"]
    assert len(outline_kps) == 1
    assert outline_kps[0]["summary"] == raw_content[:200]

    # Detail has full raw content and empty citations
    detail = events[1][1]
    assert detail["explanation"] == raw_content
    assert detail["citations"] == []


@pytest.mark.asyncio
async def test_generate_streaming_empty_content_returns_error(monkeypatch):
    """Empty LLM content returns a single error event with code EMPTY_LLM_RESPONSE."""
    _patch_chat(monkeypatch, "")

    generator = Generator()
    evidence = HybridRetrievalResult(
        anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
    )
    events = await generator.generate_streaming("测试", evidence)

    assert len(events) == 1
    assert events[0][0] == "error"
    assert events[0][1]["code"] == "EMPTY_LLM_RESPONSE"
