"""Public API: View history endpoints.

Phase 2 (Task 2.D.3): ownership scoped by ``user_id`` from the verified
Better Auth JWT instead of the legacy ``X-Device-Id`` header.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.public.v1.dependencies import require_user
from app.api.public.v1.schemas.common import PublicMeta, PublicPaginatedResponse, PublicResponse
from app.core.database import get_db
from app.models import Bridge, KnowledgePoint, ViewHistory
from app.models.current_user import CurrentUser

router = APIRouter()

VALID_HISTORY_TYPES = {"bridge", "knowledge_point"}
DEDUP_WINDOW_MINUTES = 5
MAX_HISTORY_PER_USER = 500


class HistoryRecordRequest(BaseModel):
    target_type: str
    target_id: UUID


@router.get("", response_model=PublicPaginatedResponse[dict])
def list_history(
    user: CurrentUser = Depends(require_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PublicPaginatedResponse[dict]:
    """List view history for the signed-in user, ordered by viewed_at DESC."""
    query = db.query(ViewHistory).filter(ViewHistory.user_id == user.id)
    total = query.count()
    rows = (
        query.order_by(desc(ViewHistory.viewed_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    bridge_ids = [r.target_id for r in rows if r.target_type == "bridge"]
    kp_ids = [r.target_id for r in rows if r.target_type == "knowledge_point"]

    name_map: dict[UUID, str] = {}
    if bridge_ids:
        bridges = db.query(Bridge.id, Bridge.name).filter(Bridge.id.in_(bridge_ids)).all()
        for b in bridges:
            name_map[b.id] = b.name
    if kp_ids:
        kps = db.query(KnowledgePoint.id, KnowledgePoint.name).filter(
            KnowledgePoint.id.in_(kp_ids)
        ).all()
        for kp in kps:
            name_map[kp.id] = kp.name

    items = [
        {
            "id": str(r.id),
            "target_type": r.target_type,
            "target_id": str(r.target_id),
            "target_name": name_map.get(r.target_id),
            "viewed_at": r.viewed_at.isoformat(),
        }
        for r in rows
    ]

    return PublicPaginatedResponse(
        data={"items": items},
        meta=PublicMeta(total=total, page=page, page_size=page_size),
    )


@router.post("", status_code=201, response_model=PublicResponse[dict])
def record_view(
    body: HistoryRecordRequest,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Record a view history entry with 5-min dedup and per-user cap."""
    if body.target_type not in VALID_HISTORY_TYPES:
        raise HTTPException(
            400,
            detail=(
                f"Invalid target_type: {body.target_type}. Must be one of: "
                + ", ".join(sorted(VALID_HISTORY_TYPES))
            ),
        )

    _HISTORY_TARGET_MODELS = {
        "bridge": Bridge,
        "knowledge_point": KnowledgePoint,
    }
    model_cls = _HISTORY_TARGET_MODELS.get(body.target_type)
    if model_cls and not db.query(model_cls.id).filter(model_cls.id == body.target_id).first():
        raise HTTPException(404, detail=f"{body.target_type} not found")

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    existing = (
        db.query(ViewHistory)
        .filter(
            ViewHistory.user_id == user.id,
            ViewHistory.target_type == body.target_type,
            ViewHistory.target_id == body.target_id,
            ViewHistory.viewed_at >= cutoff,
        )
        .order_by(desc(ViewHistory.viewed_at))
        .first()
    )

    if existing:
        existing.viewed_at = func.now()
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = ViewHistory(
            user_id=user.id,
            target_type=body.target_type,
            target_id=body.target_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        total = (
            db.query(func.count(ViewHistory.id))
            .filter(ViewHistory.user_id == user.id)
            .scalar()
        )
        if total and total > MAX_HISTORY_PER_USER:
            oldest_ids = (
                db.query(ViewHistory.id)
                .filter(ViewHistory.user_id == user.id)
                .order_by(desc(ViewHistory.viewed_at))
                .offset(MAX_HISTORY_PER_USER)
                .all()
            )
            if oldest_ids:
                ids_to_delete = [r[0] for r in oldest_ids]
                db.query(ViewHistory).filter(
                    ViewHistory.id.in_(ids_to_delete)
                ).delete(synchronize_session=False)
                db.commit()

    return PublicResponse(data={
        "id": str(record.id),
        "target_type": record.target_type,
        "target_id": str(record.target_id),
        "viewed_at": record.viewed_at.isoformat(),
    })
