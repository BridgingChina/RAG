"""Public API: Favorites endpoints.

Phase 2 (Task 2.D.1): ownership scoped by ``user_id`` from the verified
Better Auth JWT instead of the legacy ``X-Device-Id`` header.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.public.v1.dependencies import require_user
from app.api.public.v1.schemas.common import PublicMeta, PublicPaginatedResponse, PublicResponse
from app.core.database import get_db
from app.models import Bridge, Favorite, Flashcard, KnowledgePoint
from app.models.current_user import CurrentUser

router = APIRouter()

VALID_TYPES = {"bridge", "knowledge_point", "flashcard"}


class FavoriteAddRequest(BaseModel):
    target_type: str
    target_id: UUID


class FavoriteCheckTarget(BaseModel):
    type: str
    id: UUID


class FavoriteCheckRequest(BaseModel):
    targets: list[FavoriteCheckTarget]


@router.get("", response_model=PublicPaginatedResponse[dict])
def list_favorites(
    type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicPaginatedResponse[dict]:
    """List favorites for the signed-in user, with optional type filter."""
    query = db.query(Favorite).filter(Favorite.user_id == user.id)
    if type:
        if type not in VALID_TYPES:
            raise HTTPException(400, detail=f"Invalid type: {type}")
        query = query.filter(Favorite.target_type == type)

    total = query.count()
    favs = (
        query.order_by(Favorite.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    details: dict = {}

    bridge_ids = [f.target_id for f in favs if f.target_type == "bridge"]
    if bridge_ids:
        rows = db.query(
            Bridge.id, Bridge.name, Bridge.region, Bridge.era, Bridge.bridge_type,
        ).filter(Bridge.id.in_(bridge_ids)).all()
        for r in rows:
            summary_parts = [p for p in [r.region, f"{r.era}{r.bridge_type}" if r.era and r.bridge_type else r.era or r.bridge_type] if p]
            details[r.id] = {
                "name": r.name,
                "summary": "\uff0c".join(summary_parts) if summary_parts else None,
                "thumbnail": None,
            }

    kp_ids = [f.target_id for f in favs if f.target_type == "knowledge_point"]
    if kp_ids:
        rows = db.query(
            KnowledgePoint.id, KnowledgePoint.name, KnowledgePoint.summary,
        ).filter(KnowledgePoint.id.in_(kp_ids)).all()
        for r in rows:
            details[r.id] = {
                "name": r.name,
                "summary": (r.summary[:50] + "\u2026") if r.summary and len(r.summary) > 50 else r.summary,
                "thumbnail": None,
            }

    fc_ids = [f.target_id for f in favs if f.target_type == "flashcard"]
    if fc_ids:
        rows = db.query(
            Flashcard.id, Flashcard.front_title,
        ).filter(Flashcard.id.in_(fc_ids)).all()
        for r in rows:
            details[r.id] = {
                "name": r.front_title,
                "summary": r.front_title,
                "thumbnail": None,
            }

    data = [
        {
            "id": str(f.id),
            "target_type": f.target_type,
            "target_id": str(f.target_id),
            "target_name": (details.get(f.target_id) or {}).get("name"),
            "target_summary": (details.get(f.target_id) or {}).get("summary"),
            "thumbnail": (details.get(f.target_id) or {}).get("thumbnail"),
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in favs
    ]

    return PublicPaginatedResponse(
        data={"items": data},
        meta=PublicMeta(total=total, page=page, page_size=page_size),
    )


@router.post("", status_code=201, response_model=PublicResponse[dict])
def add_favorite(
    body: FavoriteAddRequest,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Add a favorite. Returns 409 on duplicate."""
    if body.target_type not in VALID_TYPES:
        raise HTTPException(400, detail=f"Invalid target_type: {body.target_type}")

    _TARGET_MODELS_MAP = {
        "bridge": Bridge,
        "knowledge_point": KnowledgePoint,
        "flashcard": Flashcard,
    }
    model_cls = _TARGET_MODELS_MAP.get(body.target_type)
    if model_cls and not db.query(model_cls.id).filter(model_cls.id == body.target_id).first():
        raise HTTPException(404, detail=f"{body.target_type} not found")

    fav = Favorite(
        user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
    )
    db.add(fav)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_favorite" in str(e.orig):
            raise HTTPException(409, detail="Already favorited")
        raise
    db.commit()
    db.refresh(fav)

    return PublicResponse(data={
        "id": str(fav.id),
        "target_type": fav.target_type,
        "target_id": str(fav.target_id),
        "created_at": fav.created_at.isoformat() if fav.created_at else None,
    })


@router.delete("/{favorite_id}", status_code=204)
def remove_favorite(
    favorite_id: UUID,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    """Remove a favorite. Verifies user_id ownership."""
    fav = db.query(Favorite).filter(Favorite.id == favorite_id).first()
    if not fav:
        raise HTTPException(404, detail="Favorite not found")
    if fav.user_id != user.id:
        raise HTTPException(404, detail="Favorite not found")
    db.delete(fav)
    db.commit()


@router.post(
    "/check",
    response_model=PublicResponse[dict],
    summary="Batch check favorite status (read-only)",
    description=(
        "This endpoint uses POST because it accepts a JSON request body "
        "containing a list of targets to check in batch. Despite using POST, "
        "it is a **read-only** query that does not create or modify any data."
    ),
)
def check_favorites(
    body: FavoriteCheckRequest,
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> PublicResponse[dict]:
    """Batch check which targets are favorited by the signed-in user."""
    if not body.targets:
        return PublicResponse(data={})

    target_ids = [t.id for t in body.targets]
    existing = (
        db.query(Favorite)
        .filter(
            Favorite.user_id == user.id,
            Favorite.target_id.in_(target_ids),
        )
        .all()
    )

    lookup: dict[tuple[str, UUID], Favorite] = {}
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

    return PublicResponse(data=result)
