"""Mobile API: Bridge endpoints."""
import logging
import math
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.bridge import BridgeSections, BridgeSectionLevel, MobileBridgeDetail, MobileBridgeListItem
from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse, MobileResponse
from app.api.mobile.v1.utils import escape_like as _escape_like
from app.core.database import get_db
from app.models import Bridge, Chunk, Source
from app.models.bridge_image import BridgeImage
from app.models.knowledge_point import KnowledgePoint
from app.models.knowledge_point_bridge import KnowledgePointBridge
from app.services.bridge_image_service import BridgeImageService

router = APIRouter()

LVL1_TO_SECTION: dict[str, str] = {
    "形制与技术": "structure",
    "地域与环境": "geography",
    "功能与社会": "society",
    "历史与演变": "history",
}


@router.get("")
def list_bridges(
    bridge_type: str | None = None,
    era: str | None = None,
    region: str | None = None,
    keyword: str | None = None,
    near_lat: float | None = None,
    near_lng: float | None = None,
    near_radius: int = Query(default=50000, ge=1),
    sort: str = Query(default="name", pattern="^(name|distance)$"),
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
        escaped = _escape_like(region)
        query = query.filter(Bridge.region.ilike(f"%{escaped}%"))
    if keyword:
        escaped = _escape_like(keyword)
        pattern = f"%{escaped}%"
        query = query.filter(or_(Bridge.name.ilike(pattern), Bridge.aliases.ilike(pattern)))
    if near_lat is not None and near_lng is not None:
        delta_lat = near_radius / 111_000
        # Adjust longitude delta for latitude (1° longitude ≈ 111km * cos(lat))
        delta_lng = near_radius / (111_000 * max(math.cos(math.radians(near_lat)), 0.01))
        query = query.filter(
            Bridge.latitude.isnot(None),
            Bridge.latitude.between(near_lat - delta_lat, near_lat + delta_lat),
            Bridge.longitude.between(near_lng - delta_lng, near_lng + delta_lng),
        )

    total = query.count()

    # Compute distance expression for sorting and per-item distance
    distance_expr = None
    cos_lat = 1.0
    if near_lat is not None and near_lng is not None:
        cos_lat = math.cos(math.radians(near_lat))
        distance_expr = func.sqrt(
            func.pow((Bridge.latitude - near_lat) * 111000, 2)
            + func.pow((Bridge.longitude - near_lng) * 111000 * cos_lat, 2)
        )

    if sort == "distance" and distance_expr is not None:
        query = query.order_by(distance_expr.asc())
    else:
        query = query.order_by(Bridge.name)

    bridges = query.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for b in bridges:
        dist = None
        if near_lat is not None and near_lng is not None and b.latitude is not None and b.longitude is not None:
            dlat = (b.latitude - near_lat) * 111000
            dlng = (b.longitude - near_lng) * 111000 * cos_lat
            dist = round(math.sqrt(dlat**2 + dlng**2), 1)
        items.append(
            MobileBridgeListItem(
                id=b.id, name=b.name, aliases=b.aliases, bridge_type=b.bridge_type,
                era=b.era, region=b.region, latitude=b.latitude, longitude=b.longitude,
                distance=dist,
            ).model_dump()
        )

    return MobilePaginatedResponse(
        data={"bridges": items},
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )


@router.get("/clusters")
def get_bridge_clusters(
    bounds_ne_lat: float = Query(...),
    bounds_ne_lng: float = Query(...),
    bounds_sw_lat: float = Query(...),
    bounds_sw_lng: float = Query(...),
    zoom: int = Query(..., ge=1, le=20),
    bridge_type: str | None = None,
    era: str | None = None,
    region: str | None = None,
    db: Session = Depends(get_db),
) -> MobileResponse[dict]:
    """Grid-based map clustering."""
    if bounds_sw_lat >= bounds_ne_lat:
        raise HTTPException(400, detail="bounds_sw_lat must be less than bounds_ne_lat")

    grid_size = 180.0 / (2 ** zoom)

    lat_bucket = func.floor(Bridge.latitude / grid_size)
    lng_bucket = func.floor(Bridge.longitude / grid_size)

    query = db.query(
        lat_bucket.label("lat_b"),
        lng_bucket.label("lng_b"),
        func.count().label("cnt"),
        func.avg(Bridge.latitude).label("center_lat"),
        func.avg(Bridge.longitude).label("center_lng"),
        func.min(Bridge.id).label("rep_id"),
    ).filter(
        Bridge.latitude.isnot(None),
        Bridge.latitude.between(bounds_sw_lat, bounds_ne_lat),
        Bridge.longitude.between(bounds_sw_lng, bounds_ne_lng),
    )

    if bridge_type:
        types = [t.strip() for t in bridge_type.split(",") if t.strip()]
        if types:
            query = query.filter(Bridge.bridge_type.in_(types))
    if era:
        eras = [e.strip() for e in era.split(",") if e.strip()]
        if eras:
            query = query.filter(Bridge.era.in_(eras))
    if region:
        query = query.filter(Bridge.region.ilike(f"%{_escape_like(region)}%"))

    rows = query.group_by("lat_b", "lng_b").all()

    rep_ids = [row.rep_id for row in rows]
    rep_map: dict = {}
    if rep_ids:
        reps = db.query(Bridge.id, Bridge.name, Bridge.bridge_type, Bridge.latitude, Bridge.longitude).filter(
            Bridge.id.in_(rep_ids)
        ).all()
        rep_map = {r.id: r for r in reps}

    clusters: list[dict] = []
    points: list[dict] = []

    for row in rows:
        rep = rep_map.get(row.rep_id)
        if row.cnt == 1 and rep:
            points.append({
                "id": str(rep.id), "name": rep.name, "bridge_type": rep.bridge_type,
                "latitude": rep.latitude, "longitude": rep.longitude,
            })
        else:
            clusters.append({
                "latitude": float(row.center_lat),
                "longitude": float(row.center_lng),
                "count": row.cnt,
                "representative": {"id": str(rep.id), "name": rep.name} if rep else None,
            })

    return MobileResponse(data={"clusters": clusters, "points": points})


@router.get("/{bridge_id}")
def get_bridge(bridge_id: UUID, db: Session = Depends(get_db)) -> MobileResponse[dict]:
    """Get bridge detail with sections aggregated from chunks."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(404, detail="桥梁不存在")

    # Query chunks belonging to this bridge with a recognized lvl1
    valid_lvl1 = list(LVL1_TO_SECTION.keys())
    chunks = (
        db.query(Chunk)
        .filter(Chunk.bridge_id == bridge_id, Chunk.lvl1.in_(valid_lvl1))
        .order_by(Chunk.created_at)
        .all()
    )

    # Build deduplicated sources list (preserving insertion order)
    source_ids_seen: set[UUID] = set()
    ordered_source_ids: list[UUID] = []
    for c in chunks:
        if c.source_id and c.source_id not in source_ids_seen:
            source_ids_seen.add(c.source_id)
            ordered_source_ids.append(c.source_id)

    source_map: dict[UUID, Source] = {}
    if ordered_source_ids:
        source_rows = db.query(Source).filter(Source.id.in_(ordered_source_ids)).all()
        source_map = {s.id: s for s in source_rows}

    sources_list = [
        {"id": str(sid), "title": source_map[sid].title, "type": source_map[sid].type}
        for sid in ordered_source_ids
        if sid in source_map
    ]

    # Group chunks into sections by lvl1
    section_data: dict[str, BridgeSectionLevel] = {
        sec: BridgeSectionLevel() for sec in LVL1_TO_SECTION.values()
    }
    for c in chunks:
        sec_key = LVL1_TO_SECTION.get(c.lvl1)  # type: ignore[arg-type]
        if not sec_key:
            continue
        level = section_data[sec_key]

        summary = c.section_title or (c.content[:80] + "\u2026" if len(c.content) > 80 else c.content)
        # L0: summary only
        level.l0.append({"summary": summary})
        # L1: summary + detail + citations
        l1_entry: dict = {"summary": summary, "detail": c.content}
        if c.source_id and c.source_id in source_map:
            src = source_map[c.source_id]
            l1_entry["citations"] = [{"source_id": str(src.id), "title": src.title}]
        level.l1.append(l1_entry)

    sections = BridgeSections(**section_data)

    # Tags: derive from non-null bridge attributes
    tags = [v for v in [bridge.bridge_type, bridge.material, bridge.era] if v]

    # Images: query bridge_images table
    images_rows = (
        db.query(BridgeImage)
        .filter(BridgeImage.bridge_id == bridge_id)
        .order_by(BridgeImage.order_index)
        .all()
    )
    image_list = []
    for img in images_rows:
        try:
            url = BridgeImageService.get_public_url(img.r2_key)
        except Exception:
            logger.warning("Failed to generate URL for image %s", img.id, exc_info=True)
            continue
        image_list.append({"url": url, "caption": img.caption, "type": img.type})

    # Related knowledge points via association table
    kp_links = (
        db.query(KnowledgePointBridge, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePointBridge.knowledge_point_id == KnowledgePoint.id)
        .filter(KnowledgePointBridge.bridge_id == bridge_id)
        .order_by(KnowledgePointBridge.order_index)
        .all()
    )
    related_kps = [
        {"id": str(kp.id), "name": kp.name, "relevance": link.relevance_note}
        for link, kp in kp_links
    ]

    detail = MobileBridgeDetail(
        id=bridge.id, name=bridge.name, aliases=bridge.aliases,
        bridge_type=bridge.bridge_type, era=bridge.era, region=bridge.region,
        latitude=bridge.latitude, longitude=bridge.longitude,
        tags=tags,
        images=image_list,
        sections=sections,
        related_knowledge_points=related_kps,
        sources=sources_list,
        sources_count=len(sources_list),
    )
    return MobileResponse(data=detail.model_dump())


@router.get("/{bridge_id}/knowledge-points")
def get_bridge_knowledge_points(bridge_id: UUID, db: Session = Depends(get_db)) -> MobileResponse[dict]:
    """Get knowledge points associated with a bridge."""
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(404, detail="桥梁不存在")

    kp_links = (
        db.query(KnowledgePointBridge, KnowledgePoint)
        .join(KnowledgePoint, KnowledgePointBridge.knowledge_point_id == KnowledgePoint.id)
        .filter(KnowledgePointBridge.bridge_id == bridge_id)
        .order_by(KnowledgePointBridge.order_index)
        .all()
    )
    knowledge_points = [
        {"id": str(kp.id), "name": kp.name, "line": None, "relevance": link.relevance_note}
        for link, kp in kp_links
    ]
    return MobileResponse(data={"knowledge_points": knowledge_points})
