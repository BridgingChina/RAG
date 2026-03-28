"""Admin flashcard endpoints — batch generation via LLM."""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.core.database import get_db
from app.models import Flashcard, KnowledgePoint, User
from app.providers import ZhipuProvider
from app.services.audit_service import AuditService
from app.services.flashcard_generator import FlashcardBatchGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flashcards", tags=["flashcards"])


# ── Schemas ──────────────────────────────────────────────────────────────

class BatchFlashcardRequest(BaseModel):
    knowledge_point_ids: list[UUID]


class BatchFlashcardResponse(BaseModel):
    total_generated: int
    errors: list[dict]


class FlashcardItem(BaseModel):
    id: UUID
    knowledge_point_id: UUID
    card_type: str
    front_title: str
    front_hint: str | None = None
    back_answer: str
    back_key_features: list[str] | None = None
    back_example_bridge_id: UUID | None = None


class GenerateFlashcardsResponse(BaseModel):
    generated: int
    cards: list[FlashcardItem]


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/batch-generate", response_model=BatchFlashcardResponse)
async def batch_generate_flashcards(
    body: BatchFlashcardRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchFlashcardResponse:
    """Batch generate flashcards for multiple knowledge points via LLM."""
    if not body.knowledge_point_ids:
        raise HTTPException(status_code=422, detail="knowledge_point_ids must not be empty")

    generator = FlashcardBatchGenerator()
    result = await generator.batch_generate(db, body.knowledge_point_ids)

    AuditService.log(
        db,
        action="batch_generate_flashcards",
        resource_type="flashcard",
        user_id=current_user.id,
        detail={
            "kp_count": len(body.knowledge_point_ids),
            "total_generated": result["total_generated"],
            "error_count": len(result["errors"]),
        },
        ip_address=get_client_ip(request),
    )
    db.commit()

    return BatchFlashcardResponse(**result)
