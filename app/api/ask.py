from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import AskRequest, AskResponse, CitationResponse
from app.core.database import get_db
from app.providers import ZhipuProvider
from app.services import Generator, Retriever, RetrievalContext

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
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
