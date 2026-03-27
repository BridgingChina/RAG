"""Mobile API: Favorites endpoints."""
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.mobile.v1.dependencies import require_device_id
from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse, MobileResponse
from app.core.database import get_db
from app.models import Bridge, DeviceFavorite, Flashcard, KnowledgePoint

router = APIRouter()

VALID_TYPES = {"bridge", "knowledge_point", "flashcard"}

# Name field mapping per target type
_TARGET_MODELS = {
    "bridge": (Bridge, Bridge.name),
    "knowledge_point": (KnowledgePoint, KnowledgePoint.name),
    "flashcard": (Flashcard, Flashcard.front_title),
}


class FavoriteAddRequest(BaseModel):
    target_type: str
    target_id: UUID


class FavoriteCheckTarget(BaseModel):
    type: str
    id: UUID


class FavoriteCheckRequest(BaseModel):
    targets: list[FavoriteCheckTarget]


@router.get("")
def list_favorites(
    type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobilePaginatedResponse[list[dict]]:
    """List favorites for a device, with optional type filter."""
    query = db.query(DeviceFavorite).filter(
        DeviceFavorite.device_id == device_id
    )
    if type:
        if type not in VALID_TYPES:
            raise HTTPException(400, detail=f"Invalid type: {type}")
        query = query.filter(DeviceFavorite.target_type == type)

    total = query.count()
    favs = (
        query.order_by(DeviceFavorite.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # Batch-resolve target names
    names: dict[UUID, str] = {}
    for target_type, (model, name_col) in _TARGET_MODELS.items():
        ids = [f.target_id for f in favs if f.target_type == target_type]
        if ids:
            rows = db.query(model.id, name_col).filter(model.id.in_(ids)).all()
            for row_id, row_name in rows:
                names[row_id] = row_name

    data = [
        {
            "id": str(f.id),
            "target_type": f.target_type,
            "target_id": str(f.target_id),
            "target_name": names.get(f.target_id),
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in favs
    ]

    return MobilePaginatedResponse(
        data=data,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )


@router.post("", status_code=201)
def add_favorite(
    body: FavoriteAddRequest,
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Add a favorite. Returns 409 on duplicate."""
    if body.target_type not in VALID_TYPES:
        raise HTTPException(400, detail=f"Invalid target_type: {body.target_type}")

    fav = DeviceFavorite(
        device_id=device_id,
        target_type=body.target_type,
        target_id=body.target_id,
    )
    db.add(fav)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_device_fav" in str(e.orig):
            raise HTTPException(409, detail="Already favorited")
        raise
    db.commit()
    db.refresh(fav)

    return MobileResponse(data={
        "id": str(fav.id),
        "target_type": fav.target_type,
        "target_id": str(fav.target_id),
        "created_at": fav.created_at.isoformat() if fav.created_at else None,
    })


@router.delete("/{favorite_id}", status_code=204)
def remove_favorite(
    favorite_id: UUID,
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> None:
    """Remove a favorite. Verifies device_id ownership."""
    fav = db.query(DeviceFavorite).filter(DeviceFavorite.id == favorite_id).first()
    if not fav:
        raise HTTPException(404, detail="Favorite not found")
    if fav.device_id != device_id:
        raise HTTPException(404, detail="Favorite not found")
    db.delete(fav)
    db.commit()


@router.post("/check")
def check_favorites(
    body: FavoriteCheckRequest,
    device_id: uuid.UUID = Depends(require_device_id),
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Batch check which targets are favorited."""
    if not body.targets:
        return MobileResponse(data={})

    # Query all favorites for this device matching the requested targets
    target_ids = [t.id for t in body.targets]
    existing = (
        db.query(DeviceFavorite)
        .filter(
            DeviceFavorite.device_id == device_id,
            DeviceFavorite.target_id.in_(target_ids),
        )
        .all()
    )

    # Build lookup: (target_type, target_id) -> favorite
    lookup: dict[tuple[str, UUID], DeviceFavorite] = {}
    for fav in existing:
        lookup[(fav.target_type, fav.target_id)] = fav

    result = {}
    for t in body.targets:
        key = str(t.id)
        fav = lookup.get((t.type, t.id))
        result[key] = {
            "favorited": fav is not None,
            "favorite_id": str(fav.id) if fav else None,
        }

    return MobileResponse(data=result)
