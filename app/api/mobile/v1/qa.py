"""Mobile API: SSE streaming QA endpoint."""
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.qa import QARequest
from app.core.database import get_db
from app.models import TaxonomyNode
from app.models.knowledge_point import KnowledgePoint
from app.providers import ZhipuProvider
from app.services.facet_extractor import FacetExtractor
from app.services.generator import Generator
from app.services.hybrid_retriever import (
    HybridRetriever,
    HybridRetrievalResult,
    TaxonomyFilter,
)
from app.services.tokenizer import Tokenizer, default_user_dict_path

router = APIRouter()


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_context(
    db: Session, request: QARequest,
) -> tuple[uuid.UUID | None, TaxonomyFilter | None]:
    """Resolve QA context to bridge_id or taxonomy_filter."""
    if not request.context or not request.context.type or not request.context.id:
        return None, None

    if request.context.type == "bridge":
        return request.context.id, None

    if request.context.type == "knowledge_point":
        kp = db.query(KnowledgePoint).filter(
            KnowledgePoint.id == request.context.id
        ).first()
        if kp and kp.taxonomy_node_id:
            tax_node = db.query(TaxonomyNode).filter(
                TaxonomyNode.id == kp.taxonomy_node_id
            ).first()
            if tax_node:
                return None, TaxonomyFilter(
                    lvl1=tax_node.lvl1,
                    lvl2=tax_node.lvl2,
                    lvl3=tax_node.lvl3,
                )
    return None, None


@router.post("/ask")
async def ask_sse(
    request: QARequest,
    db: Session = Depends(get_db),
):
    """SSE streaming QA endpoint.
    TODO: Upgrade to real LLM streaming.
    TODO: SSE heartbeat (15s ping) + total timeout (60s).
    """
    async def event_stream():
        qa_id = str(uuid.uuid4())
        yield _sse_event("started", {"qa_id": qa_id})

        try:
            provider = ZhipuProvider()
            tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
            retriever = HybridRetriever(provider=provider, tokenizer=tokenizer)
            generator = Generator(provider=provider)
            facet_extractor = FacetExtractor(provider=provider)

            target_bridge_id, taxonomy_filter = _resolve_context(db, request)

            if not target_bridge_id and not taxonomy_filter:
                from app.api.v1.ask import _resolve_bridge_from_question
                target_bridge_id = _resolve_bridge_from_question(db, request.question)

            facet = None
            try:
                facet = await facet_extractor.extract(request.question)
            except Exception:
                pass

            try:
                evidence = await retriever.retrieve(
                    db,
                    request.question,
                    target_bridge_id=target_bridge_id,
                    taxonomy_filter=taxonomy_filter,
                    facet=facet,
                )
            except Exception:
                evidence = HybridRetrievalResult(
                    anchor_chunks=[], concept_chunks=[], analogy_chunks=[],
                )

            if not evidence.all_chunks():
                yield _sse_event("error", {
                    "code": "INSUFFICIENT_EVIDENCE",
                    "message": "未找到直接证据，建议换一种问法或缩小范围",
                    "fallback_actions": [],
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return

            events = await generator.generate_streaming(request.question, evidence)
            for event_type, data in events:
                yield _sse_event(event_type, data)

            yield _sse_event("done", {"qa_id": qa_id})

        except Exception as e:
            yield _sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": f"服务端内部错误: {str(e)}",
            })
            yield _sse_event("done", {"qa_id": qa_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
