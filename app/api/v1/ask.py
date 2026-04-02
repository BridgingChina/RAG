"""V1 Ask API endpoint."""
import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.schemas import (
    AskRequest,
    AskResponse,
    ChannelDebugResponse,
    ChunkSummary,
    CitationResponse,
    ConfidenceResponse,
    DebugResponse,
    EvidenceGroupsResponse,
)
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator
from app.services.bridge_resolver import resolve_bridge_from_question
from app.services.facet_extractor import FacetExtractor
from app.services.generator import Confidence, GenerationResult
from app.services.hybrid_retriever import HybridRetriever, HybridRetrievalResult
from app.services.tokenizer import Tokenizer, default_user_dict_path

logger = logging.getLogger(__name__)

router = APIRouter()

_provider_cache: dict[object, object] = {}
_tokenizer_cache: dict[str | None, Tokenizer] = {}


def _get_provider():
    key = ZhipuProvider
    provider = _provider_cache.get(key)
    if provider is None:
        provider = key()
        _provider_cache[key] = provider
    return provider


def _get_tokenizer() -> Tokenizer:
    key = default_user_dict_path()
    tokenizer = _tokenizer_cache.get(key)
    if tokenizer is None:
        tokenizer = Tokenizer(user_dict_path=key)
        _tokenizer_cache[key] = tokenizer
    return tokenizer


@router.post("/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    db: Session = Depends(get_db),
    provider=Depends(_get_provider),
    tokenizer: Tokenizer = Depends(_get_tokenizer),
):
    """Ask a question and get an answer with citations.

    Uses hybrid retrieval (vector + FTS + facets) with three channels:
    - Anchor: chunks from the target bridge
    - Concept: general knowledge chunks
    - Analogy: chunks from similar bridges

    Returns confidence assessment and evidence groups.
    """
    retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
    generator = Generator(provider=provider)
    facet_extractor = FacetExtractor(provider=provider)

    degraded: list[str] = []
    want_debug = request.debug
    t_start = t_facet = t_gen = 0.0

    if want_debug:
        t_start = time.perf_counter()

    target_bridge_id = request.target_bridge_id
    if not target_bridge_id and request.context:
        target_bridge_id = request.context.bridge_id
    if not target_bridge_id:
        target_bridge_id = resolve_bridge_from_question(db, request.question)

    facet = None
    if want_debug:
        t0 = time.perf_counter()
    try:
        facet = await facet_extractor.extract(request.question)
    except Exception:
        degraded.append("facet")
    if want_debug:
        t_facet = time.perf_counter() - t0

    try:
        evidence = await retriever.retrieve(
            db,
            request.question,
            target_bridge_id=target_bridge_id,
            facet=facet,
            debug=want_debug,
        )
        degraded.extend(retriever.last_degraded)
    except Exception:
        evidence = HybridRetrievalResult(
            anchor_chunks=[], concept_chunks=[], analogy_chunks=[]
        )
        degraded.extend(retriever.last_degraded)
        degraded.append("retrieval")

    if not evidence.all_chunks():
        degraded.append("empty_evidence")

    degraded = list(dict.fromkeys(degraded))

    if want_debug:
        t0 = time.perf_counter()
    try:
        result = await generator.generate_v2(request.question, evidence)
    except Exception:
        logger.exception("LLM generation failed for question: %s", request.question[:200])
        degraded.append("generation")
        # Return a structured degraded response instead of 500
        result = GenerationResult(
            summary="抱歉，生成回答时出现错误，请稍后重试。",
            details="",
            analogy=None,
            citations=[],
            sources=[],
            confidence=Confidence(level="low", reason="LLM generation failed"),
        )
    if want_debug:
        t_gen = time.perf_counter() - t0

    evidence_groups = EvidenceGroupsResponse(
        anchor=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                bridge_id=c.bridge_id,
                bridge_name=c.bridge_name,
                preview=(
                    c.content[:100] + "..." if len(c.content) > 100 else c.content
                ),
            )
            for c in evidence.anchor_chunks
        ],
        concept=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                bridge_id=c.bridge_id,
                bridge_name=c.bridge_name,
                preview=(
                    c.content[:100] + "..." if len(c.content) > 100 else c.content
                ),
            )
            for c in evidence.concept_chunks
        ],
        analogy=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                bridge_id=c.bridge_id,
                bridge_name=c.bridge_name,
                preview=(
                    c.content[:100] + "..." if len(c.content) > 100 else c.content
                ),
            )
            for c in evidence.analogy_chunks
        ],
    )

    # Build debug response if requested
    debug_response = None
    if want_debug:
        # Merge retriever-level timings with ask-level timings
        timings: dict[str, float] = {}
        if evidence.debug and evidence.debug.timings:
            timings.update(evidence.debug.timings)
        timings["facet"] = t_facet
        timings["generate"] = t_gen
        timings["total"] = time.perf_counter() - t_start

        # Convert ChannelDebug dataclasses → ChannelDebugResponse schemas
        channels: list[ChannelDebugResponse] = []
        if evidence.debug and evidence.debug.channels:
            for cd in evidence.debug.channels:
                channels.append(
                    ChannelDebugResponse(
                        channel=cd.channel,
                        filter_desc=cd.filter_desc,
                        vec_ids=cd.vec_ids,
                        fts_ids=cd.fts_ids,
                        rrf_scores=[
                            [cid, score] for cid, score in cd.rrf_scores
                        ],
                        final_ids=cd.final_ids,
                    )
                )

        debug_response = DebugResponse(
            facet=(
                evidence.debug.facet
                if evidence.debug
                else None
            ),
            channels=channels,
            timings=timings,
        )

    return AskResponse(
        summary=result.summary,
        details=result.details,
        analogy=result.analogy,
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                source_title=c.source_title,
                page_range=c.page_range,
            )
            for c in result.citations
        ],
        sources=result.sources,
        confidence=ConfidenceResponse(
            level=result.confidence.level,
            reason=result.confidence.reason,
        ),
        evidence_groups=evidence_groups,
        degraded=degraded if degraded else None,
        debug=debug_response,
    )
