"""Mobile API: Review endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.mobile.v1.dependencies import require_device_id
from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse, MobileResponse
from app.core.database import get_db
from app.models import DeviceFavorite, DeviceReviewProgress, Flashcard

router = APIRouter()


class ReviewProgressUpdate(BaseModel):
    mastery: Literal["mastered", "needs_review"]


def _format_card(fc: Flashcard, rp: DeviceReviewProgress | None) -> dict:
    """Build card dict with front/back structure."""
    return {
        "flashcard_id": str(fc.id),
        "knowledge_point_id": str(fc.knowledge_point_id),
        "card_type": fc.card_type,
        "front": {
            "title": fc.front_title,
            "hint": fc.front_hint,
        },
        "back": {
            "answer": fc.back_answer,
            "key_features": fc.back_key_features,
            "example_bridge_id": str(fc.back_example_bridge_id) if fc.back_example_bridge_id else None,
        },
        "mastery": rp.mastery if rp else None,
        "last_reviewed_at": rp.last_reviewed_at.isoformat() if rp and rp.last_reviewed_at else None,
    }


@router.get("/today")
def get_today_queue(
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobileResponse[list[dict]]:
    """Today's review queue: favorited flashcards that need review."""
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)

    # Favorites WHERE target_type='flashcard' JOIN flashcards LEFT JOIN review_progress
    rows = (
        db.query(Flashcard, DeviceReviewProgress)
        .join(DeviceFavorite, (
            (DeviceFavorite.target_id == Flashcard.id)
            & (DeviceFavorite.target_type == "flashcard")
            & (DeviceFavorite.device_id == device_id)
        ))
        .outerjoin(DeviceReviewProgress, (
            (DeviceReviewProgress.flashcard_id == Flashcard.id)
            & (DeviceReviewProgress.device_id == device_id)
        ))
        .filter(
            (DeviceReviewProgress.id.is_(None))  # no progress yet
            | (DeviceReviewProgress.mastery == "needs_review")
            | (
                (DeviceReviewProgress.mastery == "mastered")
                & (DeviceReviewProgress.last_reviewed_at < three_days_ago)
            )
        )
        .order_by(DeviceReviewProgress.last_reviewed_at.asc().nulls_first())
        .all()
    )

    cards = [_format_card(fc, rp) for fc, rp in rows]
    return MobileResponse(data={"cards": cards, "total_due": len(cards)})


@router.get("/cards")
def list_review_cards(
    device_id: uuid.UUID = Depends(require_device_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobilePaginatedResponse[dict]:
    """All favorited flashcards with review status, paginated."""
    base = (
        db.query(Flashcard, DeviceReviewProgress)
        .join(DeviceFavorite, (
            (DeviceFavorite.target_id == Flashcard.id)
            & (DeviceFavorite.target_type == "flashcard")
            & (DeviceFavorite.device_id == device_id)
        ))
        .outerjoin(DeviceReviewProgress, (
            (DeviceReviewProgress.flashcard_id == Flashcard.id)
            & (DeviceReviewProgress.device_id == device_id)
        ))
    )

    total = base.count()
    rows = (
        base
        .order_by(Flashcard.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    cards = [_format_card(fc, rp) for fc, rp in rows]
    return MobilePaginatedResponse(
        data={"cards": cards},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )


@router.put("/progress/{flashcard_id}")
def update_review_progress(
    flashcard_id: UUID,
    body: ReviewProgressUpdate,
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Upsert review progress for a flashcard."""
    # Verify flashcard exists
    fc = db.get(Flashcard, flashcard_id)
    if not fc:
        raise HTTPException(404, detail="Flashcard not found")

    # Upsert
    rp = (
        db.query(DeviceReviewProgress)
        .filter(
            DeviceReviewProgress.device_id == device_id,
            DeviceReviewProgress.flashcard_id == flashcard_id,
        )
        .first()
    )

    now = datetime.now(timezone.utc)
    if rp:
        rp.mastery = body.mastery
        rp.last_reviewed_at = now
    else:
        rp = DeviceReviewProgress(
            device_id=device_id,
            flashcard_id=flashcard_id,
            mastery=body.mastery,
            last_reviewed_at=now,
        )
        db.add(rp)

    db.commit()
    db.refresh(rp)

    return MobileResponse(data={
        "flashcard_id": str(rp.flashcard_id),
        "mastery": rp.mastery,
        "last_reviewed_at": rp.last_reviewed_at.isoformat() if rp.last_reviewed_at else None,
    })
