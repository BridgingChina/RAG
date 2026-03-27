"""Mobile API: View history endpoints."""
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.mobile.v1.dependencies import require_device_id
from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse, MobileResponse
from app.core.database import get_db
from app.models import Bridge, DeviceViewHistory, KnowledgePoint

router = APIRouter()

VALID_HISTORY_TYPES = {"bridge", "knowledge_point"}


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
        data={"items": items},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )


@router.post("", status_code=201)
def record_view(
    body: HistoryRecordRequest,
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Record a view history entry. No dedup — each call creates a new record."""
    if body.target_type not in VALID_HISTORY_TYPES:
        raise HTTPException(400, detail=f"Invalid target_type: {body.target_type}. Must be one of: {', '.join(sorted(VALID_HISTORY_TYPES))}")

    record = DeviceViewHistory(
        device_id=device_id,
        target_type=body.target_type,
        target_id=body.target_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return MobileResponse(data={
        "id": str(record.id),
        "target_type": record.target_type,
        "target_id": str(record.target_id),
        "viewed_at": record.viewed_at.isoformat(),
    })
