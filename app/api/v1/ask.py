"""V1 Ask API endpoint."""
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.schemas import (
    AskRequest,
    AskResponse,
    ChunkSummary,
    CitationResponse,
    ConfidenceResponse,
    EvidenceGroupsResponse,
)
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator
from app.services.facet_extractor import FacetExtractor
from app.services.hybrid_retriever import HybridRetriever, HybridRetrievalResult
from app.services.tokenizer import Tokenizer

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
    key = "data/bridge_terms.txt"
    tokenizer = _tokenizer_cache.get(key)
    if tokenizer is None:
        tokenizer = Tokenizer(user_dict_path=key)
        _tokenizer_cache[key] = tokenizer
    return tokenizer


@router.post("/ask", response_model=AskResponse)
def ask(
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

    async def _run():
        degraded: list[str] = []

        target_bridge_id = request.target_bridge_id
        if not target_bridge_id and request.context:
            target_bridge_id = request.context.bridge_id

        facet = None
        try:
            facet = await facet_extractor.extract(request.question)
        except Exception:
            degraded.append("facet")

        try:
            evidence = await retriever.retrieve(
                db,
                request.question,
                target_bridge_id=target_bridge_id,
                facet=facet,
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

        result = await generator.generate_v2(request.question, evidence)

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
        )

    return asyncio.run(_run())
