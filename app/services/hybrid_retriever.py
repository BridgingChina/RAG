"""HybridRetriever - Three-channel retrieval with RRF fusion.

Implements Anchor (target bridge), Concept (general knowledge), and
Analogy (similar bridges) retrieval channels.
"""

from dataclasses import dataclass
from typing import Optional, TypedDict

from sqlalchemy import bindparam, or_, select, text
from sqlalchemy.orm import Session

from app.models import Bridge, Chunk
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


class _ChunkDetails(TypedDict):
    content: str
    bridge_id: Optional[int]
    bridge_name: str


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
        self.last_degraded: list[str] = []

    def _mark_degraded(self, key: str) -> None:
        if key not in self.last_degraded:
            self.last_degraded.append(key)

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
        self.last_degraded = []
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

        chunk_ids = [cid for cid, _ in merged]
        details_by_id = self._fetch_chunk_details(db, chunk_ids)

        # Build ChunkScore objects for diversity filtering
        chunk_scores: list[ChunkScore] = []
        for cid, score in merged:
            details = details_by_id.get(cid)
            chunk_scores.append(
                ChunkScore(
                    chunk_id=cid,
                    bridge_id=details["bridge_id"] if details else None,
                    score=score,
                )
            )

        # Apply diversity only when retrieving across multiple bridges (analogy).
        diverse = (
            apply_diversity(chunk_scores, max_per_bridge=1)
            if isinstance(bridge_filter, list)
            else chunk_scores
        )

        # Take top N and fetch full details
        top_ids = [c.chunk_id for c in diverse[:limit]]
        return self._build_retrieved_chunks(top_ids, merged, details_by_id)

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
        try:
            sql = "SELECT id FROM chunks WHERE 1=1"
            params: dict[str, object] = {"embedding": embedding_str, "limit": limit}
            bind_params: list[object] = []

            if isinstance(bridge_filter, list):
                if bridge_filter:
                    sql += " AND bridge_id IN :bridge_ids"
                    params["bridge_ids"] = bridge_filter
                    bind_params.append(bindparam("bridge_ids", expanding=True))
            elif isinstance(bridge_filter, int):
                sql += " AND bridge_id = :bridge_id"
                params["bridge_id"] = bridge_filter

            if require_no_bridge_id:
                sql += " AND bridge_id IS NULL"

            sql += " ORDER BY embedding <=> (:embedding)::vector LIMIT :limit"
            stmt = text(sql)
            if bind_params:
                stmt = stmt.bindparams(*bind_params)
            return db.execute(stmt, params).scalars().all()
        except Exception:
            self._mark_degraded("vector")
            return []

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

        try:
            # Search in both search_text and content
            sql = """
                SELECT id FROM chunks
                WHERE tsv @@ to_tsquery('simple', :tsquery)
            """
            params: dict[str, object] = {"tsquery": tsquery, "limit": limit}
            bind_params: list[object] = []

            if isinstance(bridge_filter, list):
                if bridge_filter:
                    sql += " AND bridge_id IN :bridge_ids"
                    params["bridge_ids"] = bridge_filter
                    bind_params.append(bindparam("bridge_ids", expanding=True))
            elif isinstance(bridge_filter, int):
                sql += " AND bridge_id = :bridge_id"
                params["bridge_id"] = bridge_filter

            if require_no_bridge_id:
                sql += " AND bridge_id IS NULL"

            sql += """
                ORDER BY ts_rank(tsv, to_tsquery('simple', :tsquery)) DESC
                LIMIT :limit
            """
            stmt = text(sql)
            if bind_params:
                stmt = stmt.bindparams(*bind_params)
            return db.execute(stmt, params).scalars().all()
        except Exception:
            self._mark_degraded("fts")
            return []

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

        # Build facet matching conditions
        if facet_lists["bridge_type"]:
            conditions.append(Bridge.bridge_type.in_(facet_lists["bridge_type"]))
        if facet_lists["material"]:
            conditions.append(Bridge.material.in_(facet_lists["material"]))
        if facet_lists["era"]:
            conditions.append(Bridge.era.in_(facet_lists["era"]))

        # Region uses LIKE matching (substring)
        if facet_lists["region"]:
            conditions.append(
                or_(
                    *[
                        Bridge.location.like(f"%{region}%")
                        for region in facet_lists["region"]
                    ]
                )
            )

        if not conditions:
            return []

        stmt = select(Bridge.id).where(*conditions)

        # Exclude target bridge
        if target_bridge_id is not None:
            stmt = stmt.where(Bridge.id != target_bridge_id)

        return db.execute(stmt).scalars().all()

    def _fetch_chunk_details(
        self, db: Session, chunk_ids: list[int]
    ) -> dict[int, _ChunkDetails]:
        """Fetch chunk content + bridge info for multiple chunks in one query.

        Returns:
            Dict mapping chunk_id -> {"content": str, "bridge_id": int|None, "bridge_name": str}
        """
        if not chunk_ids:
            return {}

        try:
            rows = db.execute(
                select(Chunk.id, Chunk.content, Chunk.bridge_id, Bridge.name)
                .select_from(Chunk)
                .join(Bridge, Chunk.bridge_id == Bridge.id, isouter=True)
                .where(Chunk.id.in_(chunk_ids))
            ).all()

            return {
                row[0]: {
                    "content": row[1],
                    "bridge_id": row[2],
                    "bridge_name": row[3] or "",
                }
                for row in rows
            }
        except Exception:
            self._mark_degraded("fetch_chunks")
            return {}

    def _build_retrieved_chunks(
        self,
        chunk_ids: list[int],
        scored_results: list[tuple[int, float]],
        details_by_id: dict[int, _ChunkDetails],
    ) -> list[RetrievedChunk]:
        if not chunk_ids:
            return []

        score_map = {cid: score for cid, score in scored_results}

        result: list[RetrievedChunk] = []
        for cid in chunk_ids:
            details = details_by_id.get(cid)
            if not details:
                continue
            result.append(
                RetrievedChunk(
                    chunk_id=cid,
                    content=details["content"],
                    bridge_id=details["bridge_id"],
                    bridge_name=details["bridge_name"],
                    score=float(score_map.get(cid, 0.0)),
                )
            )
        return result
