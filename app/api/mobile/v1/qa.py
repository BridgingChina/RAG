"""Mobile API: SSE pseudo-streaming QA endpoint.

Single LLM call + structured JSON split into sequential SSE events
(started -> outline -> detail* -> sources -> done). Not real token streaming.
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
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

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


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
        if not kp:
            logger.warning("QA context references non-existent knowledge_point %s", request.context.id)
            return None, None
        if not kp.taxonomy_node_id:
            logger.warning("Knowledge point %s has no taxonomy_node_id, ignoring context", kp.id)
            return None, None
        tax_node = db.query(TaxonomyNode).filter(
            TaxonomyNode.id == kp.taxonomy_node_id
        ).first()
        if not tax_node:
            logger.warning("Knowledge point %s references missing taxonomy node %s", kp.id, kp.taxonomy_node_id)
            return None, None
        return None, TaxonomyFilter(
            lvl1=tax_node.lvl1,
            lvl2=tax_node.lvl2,
            lvl3=tax_node.lvl3,
        )
    return None, None


@router.post("/ask")
@limiter.limit("10/minute")
async def ask_sse(
    request: Request,
    body: QARequest,
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

            target_bridge_id, taxonomy_filter = _resolve_context(db, body)

            if not target_bridge_id and not taxonomy_filter:
                from app.api.v1.ask import _resolve_bridge_from_question
                target_bridge_id = _resolve_bridge_from_question(db, body.question)

            facet = None
            try:
                facet = await facet_extractor.extract(body.question)
            except Exception:
                logger.warning("Facet extraction failed, continuing without facets", exc_info=True)

            try:
                evidence = await retriever.retrieve(
                    db,
                    body.question,
                    target_bridge_id=target_bridge_id,
                    taxonomy_filter=taxonomy_filter,
                    facet=facet,
                )
            except Exception:
                logger.error("Retrieval failed for question=%r", body.question, exc_info=True)
                yield _sse_event("error", {
                    "code": "RETRIEVAL_FAILED",
                    "message": "检索系统暂时不可用，请稍后重试",
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return

            if not evidence.all_chunks():
                yield _sse_event("error", {
                    "code": "INSUFFICIENT_EVIDENCE",
                    "message": "未找到直接证据，建议换一种问法或缩小范围",
                    "fallback_actions": [],
                })
                yield _sse_event("done", {"qa_id": qa_id})
                return

            events = await generator.generate_streaming(body.question, evidence)
            for event_type, data in events:
                yield _sse_event(event_type, data)

            yield _sse_event("done", {"qa_id": qa_id})

        except Exception:
            logger.error("SSE QA stream failed", exc_info=True)
            yield _sse_event("error", {
                "code": "INTERNAL_ERROR",
                "message": "服务端内部错误，请稍后重试",
            })
            yield _sse_event("done", {"qa_id": qa_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
