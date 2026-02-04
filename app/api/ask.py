from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import (
    AskRequest,
    AskResponse,
    AskResponseV2,
    ChunkSummary,
    CitationResponse,
    ConfidenceResponse,
    EvidenceGroupsResponse,
)
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator, Retriever, RetrievalContext
from app.services.hybrid_retriever import HybridRetriever, HybridRetrievalResult
from app.services.tokenizer import Tokenizer

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    """V1 endpoint - simple vector retrieval."""
    provider = ZhipuProvider()
    retriever = Retriever(provider=provider)
    generator = Generator(provider=provider)

    # Build retrieval context
    context = None
    if request.context:
        context = RetrievalContext(
            bridge_id=request.context.bridge_id,
            lvl1=request.context.lvl1,
            lvl2=request.context.lvl2,
            lvl3=request.context.lvl3,
        )

    # Retrieve evidence
    evidence = await retriever.retrieve(db, request.question, context)

    # Generate answer
    result = await generator.generate(request.question, evidence)

    return AskResponse(
        summary=result.summary,
        details=result.details,
        citations=[
            CitationResponse(
                chunk_id=c.chunk_id,
                source_title=c.source_title,
                page_range=c.page_range,
            )
            for c in result.citations
        ],
        sources=result.sources,
    )


@router.post("/ask/v2", response_model=AskResponseV2)
async def ask_v2(request: AskRequest, db: Session = Depends(get_db)):
    """V2 endpoint - hybrid retrieval with confidence."""
    provider = ZhipuProvider()
    tokenizer = Tokenizer(user_dict_path="data/bridge_terms.txt")
    retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
    generator = Generator(provider=provider)

    degraded: list[str] = []

    # Get target bridge ID
    target_bridge_id = request.target_bridge_id
    if not target_bridge_id and request.context:
        target_bridge_id = request.context.bridge_id

    # Retrieve evidence
    try:
        evidence = await retriever.retrieve(
            db, request.question, target_bridge_id=target_bridge_id
        )
    except Exception as e:
        # Fallback to empty result
        evidence = HybridRetrievalResult(
            anchor_chunks=[], concept_chunks=[], analogy_chunks=[]
        )
        degraded.append("retrieval")

    # Generate answer
    result = await generator.generate_v2(request.question, evidence)

    # Build evidence groups for response
    evidence_groups = EvidenceGroupsResponse(
        anchor=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                bridge_id=c.bridge_id,
                bridge_name=c.bridge_name,
                preview=c.content[:100] + "..." if len(c.content) > 100 else c.content,
            )
            for c in evidence.anchor_chunks
        ],
        concept=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                bridge_id=c.bridge_id,
                bridge_name=c.bridge_name,
                preview=c.content[:100] + "..." if len(c.content) > 100 else c.content,
            )
            for c in evidence.concept_chunks
        ],
        analogy=[
            ChunkSummary(
                chunk_id=c.chunk_id,
                bridge_id=c.bridge_id,
                bridge_name=c.bridge_name,
                preview=c.content[:100] + "..." if len(c.content) > 100 else c.content,
            )
            for c in evidence.analogy_chunks
        ],
    )

    return AskResponseV2(
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
