"""Tests for HybridRetriever three-channel retrieval."""

import uuid

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

# Deterministic UUIDs for tests
_UUID1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
_UUID2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
_UUID3 = uuid.UUID("00000000-0000-0000-0000-000000000003")
_UUID4 = uuid.UUID("00000000-0000-0000-0000-000000000004")
_UUID5 = uuid.UUID("00000000-0000-0000-0000-000000000005")
_UUID10 = uuid.UUID("00000000-0000-0000-0000-000000000010")
_UUID20 = uuid.UUID("00000000-0000-0000-0000-000000000020")
_UUID30 = uuid.UUID("00000000-0000-0000-0000-000000000030")
_UUID42 = uuid.UUID("00000000-0000-0000-0000-000000000042")
_UUID12 = uuid.UUID("00000000-0000-0000-0000-000000000012")
_UUID28 = uuid.UUID("00000000-0000-0000-0000-000000000028")


def test_default_quota():
    """Test DEFAULT_QUOTA has correct values."""
    assert DEFAULT_QUOTA == (6, 2, 2)


def test_retrieved_chunk_dataclass():
    """Test RetrievedChunk dataclass structure."""
    chunk = RetrievedChunk(
        chunk_id=_UUID1,
        content="Test content about Zhaozhou Bridge",
        bridge_id=_UUID10,
        bridge_name="赵州桥",
        score=0.95,
    )
    assert chunk.chunk_id == _UUID1
    assert chunk.content == "Test content about Zhaozhou Bridge"
    assert chunk.bridge_id == _UUID10
    assert chunk.bridge_name == "赵州桥"
    assert chunk.score == 0.95


def test_hybrid_retrieval_result_all_chunks():
    """Test HybridRetrievalResult.all_chunks() returns all chunks from all channels."""
    anchor = [
        RetrievedChunk(chunk_id=_UUID1, content="A1", bridge_id=_UUID10, bridge_name="Bridge A", score=0.9),
        RetrievedChunk(chunk_id=_UUID2, content="A2", bridge_id=_UUID10, bridge_name="Bridge A", score=0.8),
    ]
    concept = [
        RetrievedChunk(chunk_id=_UUID3, content="C1", bridge_id=None, bridge_name="", score=0.7),
    ]
    analogy = [
        RetrievedChunk(chunk_id=_UUID4, content="X1", bridge_id=_UUID20, bridge_name="Bridge B", score=0.6),
        RetrievedChunk(chunk_id=_UUID5, content="X2", bridge_id=_UUID30, bridge_name="Bridge C", score=0.5),
    ]

    result = HybridRetrievalResult(
        anchor_chunks=anchor,
        concept_chunks=concept,
        analogy_chunks=analogy,
    )

    all_chunks = result.all_chunks()
    assert len(all_chunks) == 5
    chunk_ids = [c.chunk_id for c in all_chunks]
    assert chunk_ids == [_UUID1, _UUID2, _UUID3, _UUID4, _UUID5]


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
        RetrievedChunk(chunk_id=_UUID1, content="赵州桥是敞肩式石拱桥", bridge_id=_UUID10, bridge_name="赵州桥", score=0.9),
        RetrievedChunk(chunk_id=_UUID2, content="建于隋代", bridge_id=_UUID10, bridge_name="赵州桥", score=0.8),
    ]
    concept = [
        RetrievedChunk(chunk_id=_UUID3, content="石拱桥的受力原理", bridge_id=None, bridge_name="", score=0.7),
    ]
    analogy = [
        RetrievedChunk(chunk_id=_UUID4, content="卢沟桥也是石拱桥", bridge_id=_UUID20, bridge_name="卢沟桥", score=0.6),
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
        filter_desc=f"bridge_id={_UUID42}",
        vec_ids=[_UUID1, _UUID2, _UUID3],
        fts_ids=[_UUID2, _UUID4],
        rrf_scores=[(_UUID2, 0.03), (_UUID1, 0.02), (_UUID3, 0.01), (_UUID4, 0.005)],
        final_ids=[_UUID2, _UUID1, _UUID3],
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
    retriever._vector_search = MagicMock(return_value=[_UUID10, _UUID20])
    retriever._fts_search = MagicMock(return_value=[_UUID20, _UUID30])
    retriever._fetch_chunk_details = MagicMock(return_value={
        _UUID10: {"content": "c10", "bridge_id": _UUID1, "bridge_name": "B1"},
        _UUID20: {"content": "c20", "bridge_id": _UUID1, "bridge_name": "B1"},
        _UUID30: {"content": "c30", "bridge_id": _UUID1, "bridge_name": "B1"},
    })

    import asyncio
    chunks, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(),
        query="test",
        query_embedding=[0.1] * 1024,
        bridge_filter=_UUID1,
        limit=3,
        debug=True,
        channel_name="anchor",
    ))
    assert isinstance(debug, ChannelDebug)
    assert debug.channel == "anchor"
    assert debug.vec_ids == [_UUID10, _UUID20]
    assert debug.fts_ids == [_UUID20, _UUID30]
    assert len(debug.final_ids) <= 3


def test_retrieve_channel_no_debug_returns_none():
    """When debug=False (default), _retrieve_channel returns (chunks, None)."""
    from unittest.mock import MagicMock
    from app.services.hybrid_retriever import HybridRetriever

    provider = MagicMock()
    retriever = HybridRetriever(provider=provider)

    retriever._vector_search = MagicMock(return_value=[_UUID10, _UUID20])
    retriever._fts_search = MagicMock(return_value=[_UUID20, _UUID30])
    retriever._fetch_chunk_details = MagicMock(return_value={
        _UUID10: {"content": "c10", "bridge_id": _UUID1, "bridge_name": "B1"},
        _UUID20: {"content": "c20", "bridge_id": _UUID1, "bridge_name": "B1"},
        _UUID30: {"content": "c30", "bridge_id": _UUID1, "bridge_name": "B1"},
    })

    import asyncio
    chunks, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(),
        query="test",
        query_embedding=[0.1] * 1024,
        bridge_filter=_UUID1,
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

    # bridge_filter=UUID
    _, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(), query="q", query_embedding=[0.1] * 1024,
        bridge_filter=_UUID42, limit=3, debug=True, channel_name="anchor",
    ))
    assert debug.filter_desc == f"bridge_id = {_UUID42}"

    # bridge_filter=list
    _, debug = asyncio.run(retriever._retrieve_channel(
        db=MagicMock(), query="q", query_embedding=[0.1] * 1024,
        bridge_filter=[_UUID5, _UUID12, _UUID28], limit=3, debug=True, channel_name="analogy",
    ))
    assert debug.filter_desc == f"bridge_id IN {[_UUID5, _UUID12, _UUID28]}"

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


def test_taxonomy_filter_dataclass():
    """Test TaxonomyFilter structure."""
    from app.services.hybrid_retriever import TaxonomyFilter

    tf = TaxonomyFilter(lvl1="形制与技术", lvl2="结构体系")
    assert tf.lvl1 == "形制与技术"
    assert tf.lvl2 == "结构体系"
    assert tf.lvl3 is None


def test_taxonomy_filter_all_none():
    """Test TaxonomyFilter with all None fields."""
    from app.services.hybrid_retriever import TaxonomyFilter

    tf = TaxonomyFilter()
    assert tf.lvl1 is None
    assert tf.lvl2 is None
    assert tf.lvl3 is None


def test_taxonomy_filter_is_empty():
    """Test TaxonomyFilter.is_empty property."""
    from app.services.hybrid_retriever import TaxonomyFilter

    tf_empty = TaxonomyFilter()
    assert tf_empty.is_empty is True

    tf_with_lvl1 = TaxonomyFilter(lvl1="形制与技术")
    assert tf_with_lvl1.is_empty is False
