"""Tests for the ranker module."""

def test_rrf_merge_basic():
    from app.services.ranker import rrf_merge
    vec_results = [1, 2, 3]
    fts_results = [2, 4, 1]
    merged = rrf_merge(vec_results, fts_results, k=60)
    assert merged[0][0] == 2  # chunk 2 appears in both, should rank highest
    assert len(merged) == 4  # unique ids: 1, 2, 3, 4


def test_rrf_merge_empty_inputs():
    from app.services.ranker import rrf_merge
    merged = rrf_merge([], [], k=60)
    assert merged == []


def test_rrf_merge_single_source():
    from app.services.ranker import rrf_merge
    vec_results = [1, 2, 3]
    merged = rrf_merge(vec_results, [], k=60)
    assert len(merged) == 3
    assert merged[0][0] == 1  # first in vec should be first


def test_apply_diversity():
    from app.services.ranker import ChunkScore, apply_diversity
    chunks = [
        ChunkScore(chunk_id=1, bridge_id=10, score=0.9),
        ChunkScore(chunk_id=2, bridge_id=10, score=0.8),  # same bridge
        ChunkScore(chunk_id=3, bridge_id=20, score=0.7),
        ChunkScore(chunk_id=4, bridge_id=20, score=0.6),  # same bridge
    ]
    result = apply_diversity(chunks, max_per_bridge=1)
    assert len(result) == 2
    bridge_ids = [c.bridge_id for c in result]
    assert len(set(bridge_ids)) == 2
