"""Tests for HybridRetriever three-channel retrieval."""

import pytest

from app.services.ranker import ChunkScore
from app.services.hybrid_retriever import (
    DEFAULT_QUOTA,
    RetrievedChunk,
    HybridRetrievalResult,
    ChannelDebug,
    RetrievalDebug,
    format_evidence_for_llm,
)


def test_default_quota():
    """Test DEFAULT_QUOTA has correct values."""
    assert DEFAULT_QUOTA == (6, 2, 2)


def test_retrieved_chunk_dataclass():
    """Test RetrievedChunk dataclass structure."""
    chunk = RetrievedChunk(
        chunk_id=1,
        content="Test content about Zhaozhou Bridge",
        bridge_id=10,
        bridge_name="赵州桥",
        score=0.95,
    )
    assert chunk.chunk_id == 1
    assert chunk.content == "Test content about Zhaozhou Bridge"
    assert chunk.bridge_id == 10
    assert chunk.bridge_name == "赵州桥"
    assert chunk.score == 0.95


def test_hybrid_retrieval_result_all_chunks():
    """Test HybridRetrievalResult.all_chunks() returns all chunks from all channels."""
    anchor = [
        RetrievedChunk(chunk_id=1, content="A1", bridge_id=10, bridge_name="Bridge A", score=0.9),
        RetrievedChunk(chunk_id=2, content="A2", bridge_id=10, bridge_name="Bridge A", score=0.8),
    ]
    concept = [
        RetrievedChunk(chunk_id=3, content="C1", bridge_id=None, bridge_name="", score=0.7),
    ]
    analogy = [
        RetrievedChunk(chunk_id=4, content="X1", bridge_id=20, bridge_name="Bridge B", score=0.6),
        RetrievedChunk(chunk_id=5, content="X2", bridge_id=30, bridge_name="Bridge C", score=0.5),
    ]

    result = HybridRetrievalResult(
        anchor_chunks=anchor,
        concept_chunks=concept,
        analogy_chunks=analogy,
    )

    all_chunks = result.all_chunks()
    assert len(all_chunks) == 5
    chunk_ids = [c.chunk_id for c in all_chunks]
    assert chunk_ids == [1, 2, 3, 4, 5]


def test_hybrid_retrieval_result_empty():
    """Test HybridRetrievalResult with empty channels."""
    result = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[],
        analogy_chunks=[],
    )
    assert len(result.all_chunks()) == 0
    assert result.anchor_chunks == []
    assert result.concept_chunks == []
    assert result.analogy_chunks == []


def test_format_evidence_for_llm():
    """Test format_evidence_for_llm formats result correctly."""
    anchor = [
        RetrievedChunk(chunk_id=1, content="赵州桥是敞肩式石拱桥", bridge_id=10, bridge_name="赵州桥", score=0.9),
        RetrievedChunk(chunk_id=2, content="建于隋代", bridge_id=10, bridge_name="赵州桥", score=0.8),
    ]
    concept = [
        RetrievedChunk(chunk_id=3, content="石拱桥的受力原理", bridge_id=None, bridge_name="", score=0.7),
    ]
    analogy = [
        RetrievedChunk(chunk_id=4, content="卢沟桥也是石拱桥", bridge_id=20, bridge_name="卢沟桥", score=0.6),
    ]

    result = HybridRetrievalResult(
        anchor_chunks=anchor,
        concept_chunks=concept,
        analogy_chunks=analogy,
    )

    formatted = format_evidence_for_llm(result)

    # Check sections are present
    assert "【本桥资料】" in formatted
    assert "【通用知识】" in formatted
    assert "【类比案例】" in formatted

    # Check chunk content is included
    assert "赵州桥是敞肩式石拱桥" in formatted
    assert "石拱桥的受力原理" in formatted
    assert "卢沟桥也是石拱桥" in formatted

    # Check bridge names are included
    assert "赵州桥" in formatted
    assert "卢沟桥" in formatted


def test_format_evidence_for_llm_empty_channels():
    """Test format_evidence_for_llm with empty channels."""
    result = HybridRetrievalResult(
        anchor_chunks=[],
        concept_chunks=[],
        analogy_chunks=[],
    )

    formatted = format_evidence_for_llm(result)

    # All sections should be present even if empty
    assert "【本桥资料】" in formatted
    assert "【通用知识】" in formatted
    assert "【类比案例】" in formatted

    # Should indicate no data
    assert "无相关资料" in formatted


def test_channel_debug_dataclass():
    """ChannelDebug holds per-channel retrieval debug info."""
    cd = ChannelDebug(
        channel="anchor",
        filter_desc="bridge_id=42",
        vec_ids=[1, 2, 3],
        fts_ids=[2, 4],
        rrf_scores=[(2, 0.03), (1, 0.02), (3, 0.01), (4, 0.005)],
        final_ids=[2, 1, 3],
    )
    assert cd.channel == "anchor"
    assert len(cd.vec_ids) == 3
    assert len(cd.rrf_scores) == 4


def test_retrieval_debug_dataclass():
    """RetrievalDebug aggregates channels and timings."""
    rd = RetrievalDebug(
        facet={"bridge_type": "拱桥"},
        channels=[],
        timings={"embed": 0.12, "anchor": 0.08},
    )
    assert rd.facet["bridge_type"] == "拱桥"
    assert rd.timings["embed"] == 0.12
