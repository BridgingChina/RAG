"""HybridRetriever - Three-channel retrieval with RRF fusion.

Implements Anchor (target bridge), Concept (general knowledge), and
Analogy (similar bridges) retrieval channels.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.constants.facets import (
    BRIDGE_TYPES,
    ERAS,
    FUNCTIONS,
    MATERIALS,
    REGIONS,
)
from app.models import Bridge
from app.providers import LLMProvider
from app.services.facet_extractor import Facet
from app.services.ranker import ChunkScore, apply_diversity, rrf_merge
from app.services.tokenizer import Tokenizer

# Default retrieval quota: (anchor, concept, analogy)
DEFAULT_QUOTA = (6, 2, 2)

# RRF constant
RRF_K = 60

# Fetch multiplier for diversity filtering
FETCH_MULTIPLIER = 3


@dataclass
class RetrievedChunk:
    """A retrieved chunk with metadata for LLM consumption."""
    chunk_id: int
    content: str
    bridge_id: Optional[int]
    bridge_name: str
    score: float


@dataclass
class HybridRetrievalResult:
    """Result of three-channel retrieval."""
    anchor_chunks: list[RetrievedChunk]
    concept_chunks: list[RetrievedChunk]
    analogy_chunks: list[RetrievedChunk]

    def all_chunks(self) -> list[RetrievedChunk]:
        """Return all chunks from all channels as a flat list."""
        return self.anchor_chunks + self.concept_chunks + self.analogy_chunks


def format_evidence_for_llm(result: HybridRetrievalResult) -> str:
    """Format retrieval result for LLM prompt with labeled sections.

    Args:
        result: HybridRetrievalResult from retrieve()

    Returns:
        Formatted string with section headers
    """
    lines = []

    # Anchor channel - target bridge specific
    lines.append("【本桥资料】")
    if result.anchor_chunks:
        for i, chunk in enumerate(result.anchor_chunks, 1):
            bridge_info = f"（{chunk.bridge_name}）" if chunk.bridge_name else ""
            lines.append(f"{i}. {chunk.content}{bridge_info}")
    else:
        lines.append("无相关资料")

    lines.append("")

    # Concept channel - general knowledge
    lines.append("【通用知识】")
    if result.concept_chunks:
        for i, chunk in enumerate(result.concept_chunks, 1):
            lines.append(f"{i}. {chunk.content}")
    else:
        lines.append("无相关资料")

    lines.append("")

    # Analogy channel - similar bridges
    lines.append("【类比案例】")
    if result.analogy_chunks:
        for i, chunk in enumerate(result.analogy_chunks, 1):
            bridge_info = f"（{chunk.bridge_name}）" if chunk.bridge_name else ""
            lines.append(f"{i}. {chunk.content}{bridge_info}")
    else:
        lines.append("无相关资料")

    return "\n".join(lines)


class HybridRetriever:
    """Three-channel hybrid retriever with RRF fusion.

    Channels:
    - Anchor: Chunks from target_bridge_id (if provided)
    - Concept: Chunks without bridge_id (general knowledge)
    - Analogy: Chunks from bridges matching facet criteria
    """

    def __init__(
        self,
        provider: LLMProvider,
        tokenizer: Optional[Tokenizer] = None,
    ):
        """Initialize HybridRetriever.

        Args:
            provider: LLMProvider for embeddings
            tokenizer: Optional Tokenizer for FTS queries
        """
        self.provider = provider
        self.tokenizer = tokenizer or Tokenizer()

    async def retrieve(
        self,
        db: Session,
        query: str,
        target_bridge_id: Optional[int] = None,
        quota: tuple[int, int, int] = DEFAULT_QUOTA,
        facet: Optional[Facet] = None,
    ) -> HybridRetrievalResult:
        """Perform three-channel retrieval.

        Args:
            db: Database session
            query: User query
            target_bridge_id: Optional target bridge for anchor channel
            quota: (anchor_limit, concept_limit, analogy_limit)
            facet: Optional Facet for analogy bridge selection

        Returns:
            HybridRetrievalResult with chunks from each channel
        """
        anchor_quota, concept_quota, analogy_quota = quota

        # Get query embedding
        embeddings = await self.provider.embed([query])
        query_embedding = embeddings[0]

        # Select candidate bridges for analogy channel
        analogy_bridge_ids = self._select_candidate_bridges(
            db, target_bridge_id, facet
        )

        # Execute three channels in parallel conceptually
        anchor_chunks = []
        if target_bridge_id is not None and anchor_quota > 0:
            anchor_chunks = await self._retrieve_channel(
                db,
                query,
                query_embedding,
                bridge_filter=target_bridge_id,
                limit=anchor_quota,
            )

        concept_chunks = []
        if concept_quota > 0:
            concept_chunks = await self._retrieve_channel(
                db,
                query,
                query_embedding,
                bridge_filter=None,
                require_no_bridge_id=True,
                limit=concept_quota,
            )

        analogy_chunks = []
        if analogy_bridge_ids and analogy_quota > 0:
            analogy_chunks = await self._retrieve_channel(
                db,
                query,
                query_embedding,
                bridge_filter=analogy_bridge_ids,
                limit=analogy_quota,
            )

        return HybridRetrievalResult(
            anchor_chunks=anchor_chunks,
            concept_chunks=concept_chunks,
            analogy_chunks=analogy_chunks,
        )

    async def _retrieve_channel(
        self,
        db: Session,
        query: str,
        query_embedding: list[float],
        bridge_filter: Optional[int | list[int]] = None,
        require_no_bridge_id: bool = False,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        """Retrieve chunks for a single channel using RRF fusion.

        Args:
            db: Database session
            query: Original query text
            query_embedding: Query vector
            bridge_filter: Single bridge_id, list of bridge_ids, or None for all
            require_no_bridge_id: If True, only return chunks without bridge_id
            limit: Number of chunks to return

        Returns:
            List of RetrievedChunk sorted by relevance
        """
        # Get more than needed for diversity filtering
        fetch_limit = limit * FETCH_MULTIPLIER

        # Run vector and FTS search in parallel
        vec_results = self._vector_search(
            db, query_embedding, bridge_filter, require_no_bridge_id, fetch_limit
        )
        fts_results = self._fts_search(
            db, query, bridge_filter, require_no_bridge_id, fetch_limit
        )

        # RRF fusion
        merged = rrf_merge(vec_results, fts_results, k=RRF_K)

        if not merged:
            return []

        # Build ChunkScore objects for diversity filtering
        # Fetch bridge_id for each chunk
        chunk_ids = [cid for cid, _ in merged]
        chunk_bridge_map = self._fetch_chunk_bridges(db, chunk_ids)

        chunk_scores = [
            ChunkScore(
                chunk_id=cid,
                bridge_id=chunk_bridge_map.get(cid),
                score=score,
            )
            for cid, score in merged
        ]

        # Apply diversity (max 1 per bridge for now)
        diverse = apply_diversity(chunk_scores, max_per_bridge=1)

        # Take top N and fetch full details
        top_ids = [c.chunk_id for c in diverse[:limit]]
        return self._fetch_retrieved_chunks(db, top_ids, merged)

    def _vector_search(
        self,
        db: Session,
        query_embedding: list[float],
        bridge_filter: Optional[int | list[int]],
        require_no_bridge_id: bool,
        limit: int,
    ) -> list[int]:
        """Perform vector similarity search using pgvector.

        Returns:
            List of chunk_ids ranked by similarity
        """
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        sql = "SELECT id FROM chunks WHERE 1=1"
        params = []

        if isinstance(bridge_filter, list):
            if bridge_filter:
                placeholders = ",".join(["%s"] * len(bridge_filter))
                sql += f" AND bridge_id IN ({placeholders})"
                params.extend(bridge_filter)
        elif isinstance(bridge_filter, int):
            sql += " AND bridge_id = %s"
            params.append(bridge_filter)

        if require_no_bridge_id:
            sql += " AND bridge_id IS NULL"

        sql += " ORDER BY embedding <=> %s::vector LIMIT %s"
        params.extend([embedding_str, limit])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()

        return [row[0] for row in rows]

    def _fts_search(
        self,
        db: Session,
        query: str,
        bridge_filter: Optional[int | list[int]],
        require_no_bridge_id: bool,
        limit: int,
    ) -> list[int]:
        """Perform full-text search using PostgreSQL GIN index.

        Returns:
            List of chunk_ids ranked by ts_rank
        """
        tsquery = self.tokenizer.to_tsquery(query)
        if not tsquery:
            return []

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        # Search in both search_text and content
        sql = """
            SELECT id FROM chunks
            WHERE tsv @@ to_tsquery('simple', %s)
        """
        params = [tsquery]

        if isinstance(bridge_filter, list):
            if bridge_filter:
                placeholders = ",".join(["%s"] * len(bridge_filter))
                sql += f" AND bridge_id IN ({placeholders})"
                params.extend(bridge_filter)
        elif isinstance(bridge_filter, int):
            sql += " AND bridge_id = %s"
            params.append(bridge_filter)

        if require_no_bridge_id:
            sql += " AND bridge_id IS NULL"

        sql += " ORDER BY ts_rank(tsv, to_tsquery('simple', %s)) DESC LIMIT %s"
        params.extend([tsquery, limit])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()

        return [row[0] for row in rows]

    def _select_candidate_bridges(
        self,
        db: Session,
        target_bridge_id: Optional[int],
        facet: Optional[Facet],
    ) -> list[int]:
        """Select candidate bridges for analogy channel based on facet matching.

        Returns:
            List of bridge_ids (excludes target_bridge_id)
        """
        if facet is None or facet.is_empty():
            return []

        facet_lists = facet.to_lists()
        conditions = []
        params = []

        # Build facet matching conditions
        for column, values in [
            ("bridge_type", facet_lists["bridge_type"]),
            ("material", facet_lists["material"]),
            ("era", facet_lists["era"]),
        ]:
            if values:
                placeholders = ",".join(["%s"] * len(values))
                conditions.append(f"{column} IN ({placeholders})")
                params.extend(values)

        # Region uses LIKE matching (substring)
        if facet_lists["region"]:
            region_conditions = []
            for region in facet_lists["region"]:
                region_conditions.append("location LIKE %s")
                params.append(f"%{region}%")
            if region_conditions:
                conditions.append(f"({' OR '.join(region_conditions)})")

        if not conditions:
            return []

        sql = "SELECT id FROM bridges WHERE " + " AND ".join(conditions)

        # Exclude target bridge
        if target_bridge_id is not None:
            sql += " AND id != %s"
            params.append(target_bridge_id)

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()

        return [row[0] for row in rows]

    def _fetch_chunk_bridges(
        self, db: Session, chunk_ids: list[int]
    ) -> dict[int, Optional[int]]:
        """Fetch bridge_id for multiple chunks.

        Returns:
            Dict mapping chunk_id -> bridge_id
        """
        if not chunk_ids:
            return {}

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        placeholders = ",".join(["%s"] * len(chunk_ids))
        sql = f"SELECT id, bridge_id FROM chunks WHERE id IN ({placeholders})"
        cursor.execute(sql, chunk_ids)
        rows = cursor.fetchall()
        cursor.close()

        return {row[0]: row[1] for row in rows}

    def _fetch_retrieved_chunks(
        self,
        db: Session,
        chunk_ids: list[int],
        scored_results: list[tuple[int, float]],
    ) -> list[RetrievedChunk]:
        """Fetch full chunk details with bridge names.

        Args:
            db: Database session
            chunk_ids: List of chunk_ids to fetch
            scored_results: List of (chunk_id, score) for scoring

        Returns:
            List of RetrievedChunk objects
        """
        if not chunk_ids:
            return []

        # Build score map
        score_map = {cid: score for cid, score in scored_results}

        raw_conn = db.connection()._dbapi_connection
        cursor = raw_conn.cursor()

        placeholders = ",".join(["%s"] * len(chunk_ids))
        sql = f"""
            SELECT c.id, c.content, c.bridge_id, b.name
            FROM chunks c
            LEFT JOIN bridges b ON c.bridge_id = b.id
            WHERE c.id IN ({placeholders})
        """
        cursor.execute(sql, chunk_ids)
        rows = cursor.fetchall()
        cursor.close()

        # Build result maintaining input order
        id_to_row = {row[0]: row for row in rows}
        result = []
        for cid in chunk_ids:
            if cid in id_to_row:
                row = id_to_row[cid]
                result.append(
                    RetrievedChunk(
                        chunk_id=row[0],
                        content=row[1],
                        bridge_id=row[2],
                        bridge_name=row[3] or "",
                        score=score_map.get(cid, 0.0),
                    )
                )
        return result
