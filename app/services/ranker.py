"""Ranker module for fusing and re-ranking retrieval results."""

import uuid
from dataclasses import dataclass


@dataclass
class ChunkScore:
    """Chunk with its retrieval score."""
    chunk_id: uuid.UUID
    bridge_id: uuid.UUID | None
    score: float


def rrf_merge(
    vec_results: list[uuid.UUID],
    fts_results: list[uuid.UUID],
    k: int = 60,
) -> list[tuple[uuid.UUID, float]]:
    """Reciprocal Rank Fusion to merge two ranked lists.

    Args:
        vec_results: Vector search results (ranked list of chunk IDs)
        fts_results: Full-text search results (ranked list of chunk IDs)
        k: RRF constant (higher = more weight to top results)

    Returns:
        List of (chunk_id, score) tuples sorted by score descending
    """
    scores: dict[uuid.UUID, float] = {}
    for rank, chunk_id in enumerate(vec_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)
    for rank, chunk_id in enumerate(fts_results, start=1):
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def apply_diversity(
    chunks: list[ChunkScore],
    max_per_bridge: int = 1,
) -> list[ChunkScore]:
    """Apply diversity constraint: max N chunks per bridge.

    This ensures results cover multiple bridges rather than clustering
    on a single bridge.

    Args:
        chunks: List of ChunkScore objects sorted by relevance
        max_per_bridge: Maximum number of chunks to keep per bridge

    Returns:
        Filtered list of ChunkScore objects
    """
    seen_bridges: dict[uuid.UUID | None, int] = {}
    result: list[ChunkScore] = []
    for chunk in chunks:
        bid = chunk.bridge_id
        count = seen_bridges.get(bid, 0)
        if count < max_per_bridge:
            result.append(chunk)
            seen_bridges[bid] = count + 1
    return result
