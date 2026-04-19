"""Public API: Review endpoints.

Phase 2 (Task 2.D.2): ``mastery`` is now a SMALLINT (0 = needs_review,
1 = mastered) instead of a VARCHAR enum, matching the SM-2 numeric state.
The response shape keeps the string mastery label for client parity, mapped
at the edge.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.public.v1.dependencies import require_user
from app.api.public.v1.schemas.common import PublicMeta, PublicPaginatedResponse, PublicResponse
from app.core.database import get_db
from app.models import Favorite, Flashcard, ReviewProgress
from app.models.current_user import CurrentUser

router = APIRouter()

# SMALLINT encoding for mastery — clients still speak the string labels.
_MASTERY_STR_TO_INT = {"needs_review": 0, "mastered": 1}
_MASTERY_INT_TO_STR = {v: k for k, v in _MASTERY_STR_TO_INT.items()}


class ReviewProgressUpdate(BaseModel):
    mastery: Literal["mastered", "needs_review"]


def _format_card(
    fc: Flashcard,
    rp: ReviewProgress | None,
    bridge_names: dict | None = None,
) -> dict:
    """Build card dict with front/back structure."""
    example_bridge = None
    if fc.back_example_bridge_id:
        bridge_name = (bridge_names or {}).get(fc.back_example_bridge_id)
        example_bridge = {"id": str(fc.back_example_bridge_id), "name": bridge_name}
    return {
        "id": str(fc.id),
        "knowledge_point_id": str(fc.knowledge_point_id),
        "card_type": fc.card_type,
        "front": {
            "title": fc.front_title,
            "hint": fc.front_hint,
        },
        "back": {
            "answer": fc.back_answer,
            "key_features": fc.back_key_features,
            "example_bridge": example_bridge,
        },
        "mastery": _MASTERY_INT_TO_STR.get(rp.mastery) if rp else None,
        "last_reviewed_at": rp.last_reviewed_at.isoformat() if rp and rp.last_reviewed_at else None,
    }


def _is_due_for_review(rp_alias) -> object:
    """SQL predicate: flashcards due for review today.

    Cards are due when there's no progress yet, the user flagged
    needs_review, or a mastered card has aged past 3 days.
    """
    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    return (
        (rp_alias.mastery.is_(None))
        | (rp_alias.mastery == _MASTERY_STR_TO_INT["needs_review"])
        | (
            (rp_alias.mastery == _MASTERY_STR_TO_INT["mastered"])
            & (rp_alias.last_reviewed_at < three_days_ago)
        )
    )


@router.get("/today", response_model=PublicPaginatedResponse[dict])
def get_today_queue(
    user: CurrentUser = Depends(require_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PublicPaginatedResponse[dict]:
    """Today's review queue: favorited flashcards that need review, paginated."""
    base = (
        db.query(Flashcard, ReviewProgress)
        .join(Favorite, (
            (Favorite.target_id == Flashcard.id)
            & (Favorite.target_type == "flashcard")
            & (Favorite.user_id == user.id)
        ))
        .outerjoin(ReviewProgress, (
            (ReviewProgress.flashcard_id == Flashcard.id)
            & (ReviewProgress.user_id == user.id)
        ))
        .filter(_is_due_for_review(ReviewProgress))
    )

    total = base.count()
    rows = (
        base
        .order_by(ReviewProgress.last_reviewed_at.asc().nulls_first())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    from app.models import Bridge
    bridge_ids = {fc.back_example_bridge_id for fc, rp in rows if fc.back_example_bridge_id}
    bridge_names: dict = {}
    if bridge_ids:
        name_rows = db.query(Bridge.id, Bridge.name).filter(Bridge.id.in_(bridge_ids)).all()
        bridge_names = {r.id: r.name for r in name_rows}
    cards = [_format_card(fc, rp, bridge_names) for fc, rp in rows]
    return PublicPaginatedResponse(
        data={"cards": cards, "total_due": total},
        meta=PublicMeta(total=total, page=page, page_size=page_size),
    )


@router.get("/cards", response_model=PublicPaginatedResponse[dict])
def list_review_cards(
    user: CurrentUser = Depends(require_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PublicPaginatedResponse[dict]:
    """All favorited flashcards with review status, paginated."""
    base = (
        db.query(Flashcard, ReviewProgress)
        .join(Favorite, (
            (Favorite.target_id == Flashcard.id)
            & (Favorite.target_type == "flashcard")
            & (Favorite.user_id == user.id)
        ))
        .outerjoin(ReviewProgress, (
            (ReviewProgress.flashcard_id == Flashcard.id)
            & (ReviewProgress.user_id == user.id)
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

    from app.models import Bridge
    bridge_ids = {fc.back_example_bridge_id for fc, rp in rows if fc.back_example_bridge_id}
    bridge_names: dict = {}
    if bridge_ids:
        name_rows = db.query(Bridge.id, Bridge.name).filter(Bridge.id.in_(bridge_ids)).all()
        bridge_names = {r.id: r.name for r in name_rows}
    cards = [_format_card(fc, rp, bridge_names) for fc, rp in rows]
    return PublicPaginatedResponse(
        data={"cards": cards},
        meta=PublicMeta(total=total, page=page, page_size=page_size),
    )


@router.put("/progress/{flashcard_id}", response_model=PublicResponse[dict])
def update_review_progress(
    flashcard_id: UUID,
    body: ReviewProgressUpdate,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Upsert review progress for a flashcard (user-scoped)."""
    fc = db.get(Flashcard, flashcard_id)
    if not fc:
        raise HTTPException(404, detail="Flashcard not found")

    rp = (
        db.query(ReviewProgress)
        .filter(
            ReviewProgress.user_id == user.id,
            ReviewProgress.flashcard_id == flashcard_id,
        )
        .first()
    )

    now = datetime.now(timezone.utc)
    mastery_int = _MASTERY_STR_TO_INT[body.mastery]
    if rp:
        rp.mastery = mastery_int
        rp.last_reviewed_at = now
    else:
        rp = ReviewProgress(
            user_id=user.id,
            flashcard_id=flashcard_id,
            mastery=mastery_int,
            last_reviewed_at=now,
        )
        db.add(rp)

    db.commit()
    db.refresh(rp)

    return PublicResponse(data={
        "flashcard_id": str(rp.flashcard_id),
        "mastery": _MASTERY_INT_TO_STR[rp.mastery],
        "reviewed_at": rp.last_reviewed_at.isoformat() if rp.last_reviewed_at else None,
    })
