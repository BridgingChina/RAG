"""Mobile API: Bridge endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.bridge import MobileBridgeDetail, MobileBridgeListItem
from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse, MobileResponse
from app.core.database import get_db
from app.models import Bridge, Chunk

router = APIRouter()


@router.get("")
def list_bridges(
    bridge_type: str | None = None,
    era: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
    near_lat: float | None = None,
    near_lng: float | None = None,
    near_radius: int = Query(default=50000, ge=1),
    sort: str = "name",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobilePaginatedResponse[dict]:
    """List bridges with filtering for mobile client."""
    query = db.query(Bridge)

    if bridge_type:
        types = [t.strip() for t in bridge_type.split(",") if t.strip()]
        if types:
            query = query.filter(Bridge.bridge_type.in_(types))
    if era:
        eras = [e.strip() for e in era.split(",") if e.strip()]
        if eras:
            query = query.filter(Bridge.era.in_(eras))
    if region:
        query = query.filter(Bridge.region.ilike(f"%{region}%"))
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(or_(Bridge.name.ilike(pattern), Bridge.aliases.ilike(pattern)))
    if near_lat is not None and near_lng is not None:
        delta_lat = near_radius / 111_000
        delta_lng = near_radius / 111_000
        query = query.filter(
            Bridge.latitude.isnot(None),
            Bridge.latitude.between(near_lat - delta_lat, near_lat + delta_lat),
            Bridge.longitude.between(near_lng - delta_lng, near_lng + delta_lng),
        )

    total = query.count()
    # TODO: sort=distance
    query = query.order_by(Bridge.name)
    bridges = query.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        MobileBridgeListItem(
            id=b.id, name=b.name, aliases=b.aliases, bridge_type=b.bridge_type,
            era=b.era, region=b.region, latitude=b.latitude, longitude=b.longitude,
        ).model_dump()
        for b in bridges
    ]

    return MobilePaginatedResponse(
        data={"bridges": items},
        meta=MobileMeta(total=total, page=page, page_size=page_size, has_more=(page * page_size < total)),
    )


@router.get("/{bridge_id}")
def get_bridge(bridge_id: UUID, db: Session = Depends(get_db)) -> MobileResponse[dict]:
    """Get bridge detail. TODO: sections aggregation (Batch 2 #17), images, related_knowledge_points."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(404, detail="桥梁不存在")

    sources_count = (
        db.query(func.count(func.distinct(Chunk.source_id)))
        .filter(Chunk.bridge_id == bridge_id)
        .scalar()
    ) or 0

    detail = MobileBridgeDetail(
        id=bridge.id, name=bridge.name, aliases=bridge.aliases,
        bridge_type=bridge.bridge_type, era=bridge.era, region=bridge.region,
        latitude=bridge.latitude, longitude=bridge.longitude,
        sources_count=sources_count,
    )
    return MobileResponse(data=detail.model_dump())


@router.get("/{bridge_id}/knowledge-points")
def get_bridge_knowledge_points(bridge_id: UUID, db: Session = Depends(get_db)) -> MobileResponse[dict]:
    """TODO (P2): Implement via knowledge_point_bridges association table."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(404, detail="桥梁不存在")
    return MobileResponse(data={"knowledge_points": []})
