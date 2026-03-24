"""Tests for the ranker module."""

import uuid

_UUID1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
_UUID2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
_UUID3 = uuid.UUID("00000000-0000-0000-0000-000000000003")
_UUID4 = uuid.UUID("00000000-0000-0000-0000-000000000004")
_UUID10 = uuid.UUID("00000000-0000-0000-0000-000000000010")
_UUID20 = uuid.UUID("00000000-0000-0000-0000-000000000020")


def test_rrf_merge_basic():
    from app.services.ranker import rrf_merge
    vec_results = [_UUID1, _UUID2, _UUID3]
    fts_results = [_UUID2, _UUID4, _UUID1]
    merged = rrf_merge(vec_results, fts_results, k=60)
    assert merged[0][0] == _UUID2  # chunk 2 appears in both, should rank highest
    assert len(merged) == 4  # unique ids: 1, 2, 3, 4


def test_rrf_merge_empty_inputs():
    from app.services.ranker import rrf_merge
    merged = rrf_merge([], [], k=60)
    assert merged == []


def test_rrf_merge_single_source():
    from app.services.ranker import rrf_merge
    vec_results = [_UUID1, _UUID2, _UUID3]
    merged = rrf_merge(vec_results, [], k=60)
    assert len(merged) == 3
    assert merged[0][0] == _UUID1  # first in vec should be first


def test_apply_diversity():
    from app.services.ranker import ChunkScore, apply_diversity
    chunks = [
        ChunkScore(chunk_id=_UUID1, bridge_id=_UUID10, score=0.9),
        ChunkScore(chunk_id=_UUID2, bridge_id=_UUID10, score=0.8),  # same bridge
        ChunkScore(chunk_id=_UUID3, bridge_id=_UUID20, score=0.7),
        ChunkScore(chunk_id=_UUID4, bridge_id=_UUID20, score=0.6),  # same bridge
    ]
    result = apply_diversity(chunks, max_per_bridge=1)
    assert len(result) == 2
    bridge_ids = [c.bridge_id for c in result]
    assert len(set(bridge_ids)) == 2
