"""Mobile API: View history endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.mobile.v1.dependencies import require_device_id
from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse, MobileResponse
from app.core.database import get_db
from app.models import Bridge, DeviceViewHistory, KnowledgePoint

router = APIRouter()

VALID_HISTORY_TYPES = {"bridge", "knowledge_point"}
DEDUP_WINDOW_MINUTES = 5
MAX_HISTORY_PER_DEVICE = 500


class HistoryRecordRequest(BaseModel):
    target_type: str
    target_id: UUID


@router.get("")
def list_history(
    device_id: uuid.UUID = Depends(require_device_id),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobilePaginatedResponse[dict]:
    """List view history for a device, ordered by viewed_at DESC."""
    query = db.query(DeviceViewHistory).filter(
        DeviceViewHistory.device_id == device_id
    )
    total = query.count()
    rows = (
        query.order_by(desc(DeviceViewHistory.viewed_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Batch-resolve target names
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

    return MobilePaginatedResponse(
        data=items,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )


@router.post("", status_code=201)
def record_view(
    body: HistoryRecordRequest,
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Record a view history entry with 5-min dedup and 500-record per-device cap."""
    if body.target_type not in VALID_HISTORY_TYPES:
        raise HTTPException(400, detail=f"Invalid target_type: {body.target_type}. Must be one of: {', '.join(sorted(VALID_HISTORY_TYPES))}")

    # Verify target exists
    _HISTORY_TARGET_MODELS = {
        "bridge": Bridge,
        "knowledge_point": KnowledgePoint,
    }
    model_cls = _HISTORY_TARGET_MODELS.get(body.target_type)
    if model_cls and not db.query(model_cls.id).filter(model_cls.id == body.target_id).first():
        raise HTTPException(404, detail=f"{body.target_type} not found")

    # Dedup: if same target viewed within DEDUP_WINDOW_MINUTES, update viewed_at
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=DEDUP_WINDOW_MINUTES)
    existing = (
        db.query(DeviceViewHistory)
        .filter(
            DeviceViewHistory.device_id == device_id,
            DeviceViewHistory.target_type == body.target_type,
            DeviceViewHistory.target_id == body.target_id,
            DeviceViewHistory.viewed_at >= cutoff,
        )
        .order_by(desc(DeviceViewHistory.viewed_at))
        .first()
    )

    if existing:
        existing.viewed_at = func.now()
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = DeviceViewHistory(
            device_id=device_id,
            target_type=body.target_type,
            target_id=body.target_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # Enforce per-device limit
        total = (
            db.query(func.count(DeviceViewHistory.id))
            .filter(DeviceViewHistory.device_id == device_id)
            .scalar()
        )
        if total and total > MAX_HISTORY_PER_DEVICE:
            # Delete oldest records exceeding the cap
            oldest_ids = (
                db.query(DeviceViewHistory.id)
                .filter(DeviceViewHistory.device_id == device_id)
                .order_by(desc(DeviceViewHistory.viewed_at))
                .offset(MAX_HISTORY_PER_DEVICE)
                .all()
            )
            if oldest_ids:
                ids_to_delete = [r[0] for r in oldest_ids]
                db.query(DeviceViewHistory).filter(
                    DeviceViewHistory.id.in_(ids_to_delete)
                ).delete(synchronize_session=False)
                db.commit()

    return MobileResponse(data={
        "id": str(record.id),
        "target_type": record.target_type,
        "target_id": str(record.target_id),
        "viewed_at": record.viewed_at.isoformat(),
    })
