"""HybridRetriever - Three-channel retrieval with RRF fusion.

Implements Anchor (target bridge), Concept (general knowledge), and
Analogy (similar bridges) retrieval channels.
"""

import logging
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Optional, TypedDict

from sqlalchemy import bindparam, or_, select, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

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
    bridge_id: Optional[uuid.UUID]
    bridge_name: str


@dataclass
class RetrievedChunk:
    """A retrieved chunk with metadata for LLM consumption."""
    chunk_id: uuid.UUID
    content: str
    bridge_id: Optional[uuid.UUID]
    bridge_name: str
    score: float


@dataclass
class TaxonomyFilter:
    """Filter chunks by taxonomy labels.

    Only non-None fields are applied as AND conditions, so setting lvl1
    alone matches all chunks under that line.
    """
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.lvl1 or self.lvl2 or self.lvl3)


@dataclass
class ChannelDebug:
    """Debug info for a single retrieval channel."""
    channel: str                                  # "anchor" | "concept" | "analogy"
    filter_desc: str                              # e.g. "bridge_id=..."
    vec_ids: list[uuid.UUID]                      # vector search raw results
    fts_ids: list[uuid.UUID]                      # FTS raw results
    rrf_scores: list[tuple[uuid.UUID, float]]     # after RRF merge
    final_ids: list[uuid.UUID]                    # after diversity + limit


@dataclass
class RetrievalDebug:
    """Full debug info for a retrieval request."""
    facet: dict | None
    channels: list[ChannelDebug]
    timings: dict[str, float]  # stage -> seconds


@dataclass
class HybridRetrievalResult:
    """Result of three-channel retrieval."""
    anchor_chunks: list[RetrievedChunk]
    concept_chunks: list[RetrievedChunk]
    analogy_chunks: list[RetrievedChunk]
    debug: RetrievalDebug | None = None

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
        target_bridge_id: Optional[uuid.UUID] = None,
        taxonomy_filter: Optional[TaxonomyFilter] = None,
        quota: tuple[int, int, int] = DEFAULT_QUOTA,
        facet: Optional[Facet] = None,
        debug: bool = False,
    ) -> HybridRetrievalResult:
        """Perform three-channel retrieval.

        Args:
            db: Database session
            query: User query
            target_bridge_id: Optional target bridge for anchor channel
            taxonomy_filter: Optional TaxonomyFilter for taxonomy-scoped anchor
                retrieval (used when context is a knowledge_point)
            quota: (anchor_limit, concept_limit, analogy_limit)
            facet: Optional Facet for analogy bridge selection
            debug: If True, populate result.debug with RetrievalDebug

        Returns:
            HybridRetrievalResult with chunks from each channel
        """
        self.last_degraded = []
        anchor_quota, concept_quota, analogy_quota = quota
        timings: dict[str, float] = {}
        channel_debugs: list[ChannelDebug] = []

        # Get query embedding
        if debug:
            t0 = time.perf_counter()
        embeddings = await self.provider.embed([query])
        query_embedding = embeddings[0]
        if debug:
            timings["embed"] = time.perf_counter() - t0

        # Select candidate bridges for analogy channel
        analogy_bridge_ids = self._select_candidate_bridges(
            db, target_bridge_id, facet
        )

        # Execute three channels
        anchor_chunks: list[RetrievedChunk] = []
        if anchor_quota > 0 and (target_bridge_id is not None or (taxonomy_filter is not None and not taxonomy_filter.is_empty)):
            if debug:
                t0 = time.perf_counter()
            anchor_chunks, anchor_dbg = await self._retrieve_channel(
                db,
                query,
                query_embedding,
                bridge_filter=target_bridge_id,
                taxonomy_filter=taxonomy_filter if target_bridge_id is None else None,
                limit=anchor_quota,
                debug=debug,
                channel_name="anchor",
            )
            if debug:
                timings["anchor"] = time.perf_counter() - t0
                if anchor_dbg:
                    channel_debugs.append(anchor_dbg)

        concept_chunks: list[RetrievedChunk] = []
        if concept_quota > 0:
            if debug:
                t0 = time.perf_counter()
            concept_chunks, concept_dbg = await self._retrieve_channel(
                db,
                query,
                query_embedding,
                bridge_filter=None,
                require_no_bridge_id=True,
                limit=concept_quota,
                debug=debug,
                channel_name="concept",
            )
            if debug:
                timings["concept"] = time.perf_counter() - t0
                if concept_dbg:
                    channel_debugs.append(concept_dbg)

        analogy_chunks: list[RetrievedChunk] = []
        if analogy_bridge_ids and analogy_quota > 0:
            if debug:
                t0 = time.perf_counter()
            analogy_chunks, analogy_dbg = await self._retrieve_channel(
                db,
                query,
                query_embedding,
                bridge_filter=analogy_bridge_ids,
                limit=analogy_quota,
                debug=debug,
                channel_name="analogy",
            )
            if debug:
                timings["analogy"] = time.perf_counter() - t0
                if analogy_dbg:
                    channel_debugs.append(analogy_dbg)

        result = HybridRetrievalResult(
            anchor_chunks=anchor_chunks,
            concept_chunks=concept_chunks,
            analogy_chunks=analogy_chunks,
        )

        if debug:
            result.debug = RetrievalDebug(
                facet=asdict(facet) if facet else None,
                channels=channel_debugs,
                timings=timings,
            )

        return result

    async def _retrieve_channel(
        self,
        db: Session,
        query: str,
        query_embedding: list[float],
        bridge_filter: Optional[uuid.UUID | list[uuid.UUID]] = None,
        require_no_bridge_id: bool = False,
        taxonomy_filter: Optional[TaxonomyFilter] = None,
        limit: int = 10,
        debug: bool = False,
        channel_name: str = "",
    ) -> tuple[list[RetrievedChunk], ChannelDebug | None]:
        """Retrieve chunks for a single channel using RRF fusion.

        Args:
            db: Database session
            query: Original query text
            query_embedding: Query vector
            bridge_filter: Single bridge_id, list of bridge_ids, or None for all
            require_no_bridge_id: If True, only return chunks without bridge_id
            limit: Number of chunks to return
            debug: If True, return ChannelDebug alongside chunks
            channel_name: Channel label for debug output

        Returns:
            Tuple of (chunks, ChannelDebug | None)
        """
        # Get more than needed for diversity filtering
        fetch_limit = limit * FETCH_MULTIPLIER

        # Run vector and FTS search sequentially
        vec_results = self._vector_search(
            db, query_embedding, bridge_filter, require_no_bridge_id, fetch_limit,
            taxonomy_filter=taxonomy_filter,
        )
        fts_results = self._fts_search(
            db, query, bridge_filter, require_no_bridge_id, fetch_limit,
            taxonomy_filter=taxonomy_filter,
        )

        # RRF fusion
        merged = rrf_merge(vec_results, fts_results, k=RRF_K)

        if not merged:
            if debug:
                filter_desc = self._build_filter_desc(bridge_filter, require_no_bridge_id)
                return [], ChannelDebug(
                    channel=channel_name,
                    filter_desc=filter_desc,
                    vec_ids=list(vec_results),
                    fts_ids=list(fts_results),
                    rrf_scores=[],
                    final_ids=[],
                )
            return [], None

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
        chunks = self._build_retrieved_chunks(top_ids, merged, details_by_id)

        if debug:
            filter_desc = self._build_filter_desc(bridge_filter, require_no_bridge_id)
            return chunks, ChannelDebug(
                channel=channel_name,
                filter_desc=filter_desc,
                vec_ids=list(vec_results),
                fts_ids=list(fts_results),
                rrf_scores=list(merged),
                final_ids=top_ids,
            )
        return chunks, None

    @staticmethod
    def _build_filter_desc(
        bridge_filter: Optional[uuid.UUID | list[uuid.UUID]],
        require_no_bridge_id: bool = False,
    ) -> str:
        """Build a human-readable filter description for debug output."""
        if isinstance(bridge_filter, uuid.UUID):
            return f"bridge_id = {bridge_filter}"
        if isinstance(bridge_filter, list):
            return f"bridge_id IN {bridge_filter}"
        if require_no_bridge_id:
            return "bridge_id IS NULL"
        return "(no filter)"

    def _vector_search(
        self,
        db: Session,
        query_embedding: list[float],
        bridge_filter: Optional[uuid.UUID | list[uuid.UUID]],
        require_no_bridge_id: bool,
        limit: int,
        taxonomy_filter: Optional[TaxonomyFilter] = None,
    ) -> list[uuid.UUID]:
        """Perform vector similarity search using pgvector.

        Returns:
            List of chunk_ids ranked by similarity
        """
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        try:
            sql = "SELECT id FROM chunks WHERE needs_reindex = false"
            params: dict[str, object] = {"embedding": embedding_str, "limit": limit}
            bind_params: list[object] = []

            if isinstance(bridge_filter, list):
                if bridge_filter:
                    sql += " AND bridge_id IN :bridge_ids"
                    params["bridge_ids"] = bridge_filter
                    bind_params.append(bindparam("bridge_ids", expanding=True))
            elif isinstance(bridge_filter, uuid.UUID):
                sql += " AND bridge_id = :bridge_id"
                params["bridge_id"] = bridge_filter

            if require_no_bridge_id:
                sql += " AND bridge_id IS NULL"

            if taxonomy_filter:
                if taxonomy_filter.lvl1:
                    sql += " AND lvl1 = :tax_lvl1"
                    params["tax_lvl1"] = taxonomy_filter.lvl1
                if taxonomy_filter.lvl2:
                    sql += " AND lvl2 = :tax_lvl2"
                    params["tax_lvl2"] = taxonomy_filter.lvl2
                if taxonomy_filter.lvl3:
                    sql += " AND lvl3 = :tax_lvl3"
                    params["tax_lvl3"] = taxonomy_filter.lvl3

            sql += " ORDER BY embedding <=> (:embedding)::vector LIMIT :limit"
            stmt = text(sql)
            if bind_params:
                stmt = stmt.bindparams(*bind_params)
            return db.execute(stmt, params).scalars().all()
        except Exception:
            logger.error("Vector search failed", exc_info=True)
            self._mark_degraded("vector")
            return []

    def _fts_search(
        self,
        db: Session,
        query: str,
        bridge_filter: Optional[uuid.UUID | list[uuid.UUID]],
        require_no_bridge_id: bool,
        limit: int,
        taxonomy_filter: Optional[TaxonomyFilter] = None,
    ) -> list[uuid.UUID]:
        """Perform full-text search using PostgreSQL GIN index.

        Returns:
            List of chunk_ids ranked by ts_rank
        """
        tsquery = self.tokenizer.to_tsquery(query)
        if not tsquery:
            return []

        try:
            # Full-text search using pre-computed tsv column
            sql = """
                SELECT id FROM chunks
                WHERE needs_reindex = false
                  AND tsv @@ to_tsquery('simple', :tsquery)
            """
            params: dict[str, object] = {"tsquery": tsquery, "limit": limit}
            bind_params: list[object] = []

            if isinstance(bridge_filter, list):
                if bridge_filter:
                    sql += " AND bridge_id IN :bridge_ids"
                    params["bridge_ids"] = bridge_filter
                    bind_params.append(bindparam("bridge_ids", expanding=True))
            elif isinstance(bridge_filter, uuid.UUID):
                sql += " AND bridge_id = :bridge_id"
                params["bridge_id"] = bridge_filter

            if require_no_bridge_id:
                sql += " AND bridge_id IS NULL"

            if taxonomy_filter:
                if taxonomy_filter.lvl1:
                    sql += " AND lvl1 = :tax_lvl1"
                    params["tax_lvl1"] = taxonomy_filter.lvl1
                if taxonomy_filter.lvl2:
                    sql += " AND lvl2 = :tax_lvl2"
                    params["tax_lvl2"] = taxonomy_filter.lvl2
                if taxonomy_filter.lvl3:
                    sql += " AND lvl3 = :tax_lvl3"
                    params["tax_lvl3"] = taxonomy_filter.lvl3

            sql += """
                ORDER BY ts_rank(tsv, to_tsquery('simple', :tsquery)) DESC
                LIMIT :limit
            """
            stmt = text(sql)
            if bind_params:
                stmt = stmt.bindparams(*bind_params)
            return db.execute(stmt, params).scalars().all()
        except Exception:
            logger.error("FTS search failed", exc_info=True)
            self._mark_degraded("fts")
            return []

    def _select_candidate_bridges(
        self,
        db: Session,
        target_bridge_id: Optional[uuid.UUID],
        facet: Optional[Facet],
    ) -> list[uuid.UUID]:
        """Select candidate bridges for analogy channel based on facet matching.

        Returns:
            List of bridge_ids (excludes target_bridge_id)
        """
        if facet is None or facet.is_empty():
            return []

        facet_lists = facet.to_lists()
        conditions = []
        function_condition = None

        # Build facet matching conditions
        if facet_lists["bridge_type"]:
            conditions.append(Bridge.bridge_type.in_(facet_lists["bridge_type"]))
        if facet_lists["material"]:
            conditions.append(Bridge.material.in_(facet_lists["material"]))
        if facet_lists["era"]:
            conditions.append(Bridge.era.in_(facet_lists["era"]))
        if facet_lists["function"]:
            function_condition = Bridge.function.in_(facet_lists["function"])

        # Region uses LIKE matching (substring)
        if facet_lists["region"]:
            conditions.append(
                or_(
                    *[
                        Bridge.region.like(f"%{region}%")
                        for region in facet_lists["region"]
                    ]
                )
            )

        if not conditions and function_condition is None:
            return []

        all_conditions = [*conditions, *([function_condition] if function_condition is not None else [])]
        stmt = select(Bridge.id).where(*all_conditions)

        # Exclude target bridge
        if target_bridge_id is not None:
            stmt = stmt.where(Bridge.id != target_bridge_id)

        ids = db.execute(stmt).scalars().all()
        # Best-effort fallback: if the DB has no/insufficient bridge.function data yet,
        # avoid making analogy selection worse by dropping the function condition.
        if not ids and function_condition is not None and conditions:
            fallback_stmt = select(Bridge.id).where(*conditions)
            if target_bridge_id is not None:
                fallback_stmt = fallback_stmt.where(Bridge.id != target_bridge_id)
            return db.execute(fallback_stmt).scalars().all()

        return ids

    def _fetch_chunk_details(
        self, db: Session, chunk_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, _ChunkDetails]:
        """Fetch chunk content + bridge info for multiple chunks in one query.

        Returns:
            Dict mapping chunk_id (UUID) -> _ChunkDetails
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
            logger.error("Chunk detail fetch failed", exc_info=True)
            self._mark_degraded("fetch_chunks")
            return {}

    def _build_retrieved_chunks(
        self,
        chunk_ids: list[uuid.UUID],
        scored_results: list[tuple[uuid.UUID, float]],
        details_by_id: dict[uuid.UUID, _ChunkDetails],
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
