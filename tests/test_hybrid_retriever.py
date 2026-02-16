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


def test_retrieve_channel_returns_debug_tuple():
    """When debug=True, _retrieve_channel returns (chunks, ChannelDebug)."""
    from unittest.mock import MagicMock
    from app.services.hybrid_retriever import HybridRetriever, ChannelDebug

    provider = MagicMock()
    retriever = HybridRetriever(provider=provider)

    # Mock internal methods to avoid DB
    retriever._vector_search = MagicMock(return_value=[10, 20])
    retriever._fts_search = MagicMock(return_value=[20, 30])
    retriever._fetch_chunk_details = MagicMock(return_value={
        10: {"content": "c10", "bridge_id": 1, "bridge_name": "B1"},
        20: {"content": "c20", "bridge_id": 1, "bridge_name": "B1"},
        30: {"content": "c30", "bridge_id": 1, "bridge_name": "B1"},
    })

    import asyncio
    chunks, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(),
        query="test",
        query_embedding=[0.1] * 1024,
        bridge_filter=1,
        limit=3,
        debug=True,
        channel_name="anchor",
    ))
    assert isinstance(debug, ChannelDebug)
    assert debug.channel == "anchor"
    assert debug.vec_ids == [10, 20]
    assert debug.fts_ids == [20, 30]
    assert len(debug.final_ids) <= 3


def test_retrieve_channel_no_debug_returns_none():
    """When debug=False (default), _retrieve_channel returns (chunks, None)."""
    from unittest.mock import MagicMock
    from app.services.hybrid_retriever import HybridRetriever

    provider = MagicMock()
    retriever = HybridRetriever(provider=provider)

    retriever._vector_search = MagicMock(return_value=[10, 20])
    retriever._fts_search = MagicMock(return_value=[20, 30])
    retriever._fetch_chunk_details = MagicMock(return_value={
        10: {"content": "c10", "bridge_id": 1, "bridge_name": "B1"},
        20: {"content": "c20", "bridge_id": 1, "bridge_name": "B1"},
        30: {"content": "c30", "bridge_id": 1, "bridge_name": "B1"},
    })

    import asyncio
    chunks, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(),
        query="test",
        query_embedding=[0.1] * 1024,
        bridge_filter=1,
        limit=3,
    ))
    assert debug is None
    assert isinstance(chunks, list)


def test_retrieve_channel_debug_filter_desc_variants():
    """filter_desc is built correctly for different bridge_filter values."""
    from unittest.mock import MagicMock
    from app.services.hybrid_retriever import HybridRetriever

    provider = MagicMock()
    retriever = HybridRetriever(provider=provider)

    retriever._vector_search = MagicMock(return_value=[])
    retriever._fts_search = MagicMock(return_value=[])
    retriever._fetch_chunk_details = MagicMock(return_value={})

    import asyncio

    # bridge_filter=int
    _, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(), query="q", query_embedding=[0.1] * 1024,
        bridge_filter=42, limit=3, debug=True, channel_name="anchor",
    ))
    assert debug.filter_desc == "bridge_id = 42"

    # bridge_filter=list
    _, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(), query="q", query_embedding=[0.1] * 1024,
        bridge_filter=[5, 12, 28], limit=3, debug=True, channel_name="analogy",
    ))
    assert debug.filter_desc == "bridge_id IN [5, 12, 28]"

    # require_no_bridge_id=True
    _, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(), query="q", query_embedding=[0.1] * 1024,
        require_no_bridge_id=True, limit=3, debug=True, channel_name="concept",
    ))
    assert debug.filter_desc == "bridge_id IS NULL"

    # no filter
    _, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(), query="q", query_embedding=[0.1] * 1024,
        limit=3, debug=True, channel_name="test",
    ))
    assert debug.filter_desc == "(no filter)"
