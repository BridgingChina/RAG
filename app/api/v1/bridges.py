"""Bridges CRUD API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.v1.schemas.bridge import (
    BridgeCreate,
    BridgeDetail,
    BridgeListItem,
    BridgeMergeRequest,
    BridgeUpdate,
)
from app.api.v1.schemas.chunk import ChunkListItem
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models import Bridge, Chunk, ChunkBridgeLink, Source

router = APIRouter(prefix="/bridges", tags=["bridges"])


@router.get("", response_model=PaginatedResponse[BridgeListItem])
def list_bridges(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[BridgeListItem]:
    """List all bridges with optional name search and chunk count."""
    # Build base query with chunk count
    query = (
        db.query(
            Bridge.id,
            Bridge.name,
            Bridge.aliases,
            Bridge.bridge_type,
            Bridge.material,
            Bridge.era,
            Bridge.location,
            Bridge.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Bridge.id == Chunk.bridge_id)
        .group_by(Bridge.id)
    )

    # Apply search filter
    if q is not None:
        query = query.filter(Bridge.name.ilike(f"%{q}%"))

    # Get total count (Query.count wraps grouped query as subquery)
    total = query.count()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    results = query.order_by(Bridge.name).offset(offset).limit(page_size).all()

    # Build response items
    items = [
        BridgeListItem(
            id=row.id,
            name=row.name,
            aliases=row.aliases,
            bridge_type=row.bridge_type,
            material=row.material,
            era=row.era,
            location=row.location,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
        )
        for row in results
    ]

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{bridge_id}", response_model=BridgeDetail)
def get_bridge(bridge_id: int, db: Session = Depends(get_db)) -> BridgeDetail:
    """Get detailed information about a specific bridge."""
    # Fetch the bridge
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    # Count associated chunks
    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.bridge_id == bridge_id).scalar()

    return BridgeDetail(
        id=bridge.id,
        name=bridge.name,
        aliases=bridge.aliases,
        bridge_type=bridge.bridge_type,
        material=bridge.material,
        era=bridge.era,
        location=bridge.location,
        function=bridge.function,
        summary=bridge.summary,
        chunk_count=chunk_count,
        created_at=bridge.created_at,
    )


@router.post("", response_model=BridgeDetail, status_code=201)
def create_bridge(
    body: BridgeCreate, db: Session = Depends(get_db)
) -> BridgeDetail:
    """Create a new bridge."""
    # Create the bridge
    bridge = Bridge(**body.model_dump())
    db.add(bridge)
    db.commit()
    db.refresh(bridge)

    # Return detail with chunk_count = 0 for new bridge
    return BridgeDetail(
        id=bridge.id,
        name=bridge.name,
        aliases=bridge.aliases,
        bridge_type=bridge.bridge_type,
        material=bridge.material,
        era=bridge.era,
        location=bridge.location,
        function=bridge.function,
        summary=bridge.summary,
        chunk_count=0,
        created_at=bridge.created_at,
    )


@router.put("/{bridge_id}", response_model=BridgeDetail)
def update_bridge(
    bridge_id: int, body: BridgeUpdate, db: Session = Depends(get_db)
) -> BridgeDetail:
    """Update a bridge's metadata."""
    # Fetch the bridge
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    # Get update data, excluding unset fields
    update_data = body.model_dump(exclude_unset=True)

    # Apply updates
    for key, value in update_data.items():
        setattr(bridge, key, value)

    db.commit()
    db.refresh(bridge)

    # Return full detail using the get endpoint
    return get_bridge(bridge_id, db)


@router.delete("/{bridge_id}", status_code=204)
def delete_bridge(bridge_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a bridge if it has no associated chunks."""
    # Fetch the bridge
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    # Check for associated chunks (primary binding)
    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.bridge_id == bridge_id).scalar()
    if chunk_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete bridge with {chunk_count} associated chunks",
        )

    # Delete any secondary bridge links referencing this bridge
    db.query(ChunkBridgeLink).filter(
        ChunkBridgeLink.bridge_id == bridge_id
    ).delete(synchronize_session=False)

    # Delete the bridge
    db.delete(bridge)
    db.commit()


@router.get("/{bridge_id}/chunks", response_model=PaginatedResponse[ChunkListItem])
def get_bridge_chunks(
    bridge_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PaginatedResponse[ChunkListItem]:
    """Get chunks associated with a specific bridge (paginated)."""
    # Check if bridge exists
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")

    # Base query for chunks of this bridge
    query = (
        db.query(
            Chunk.id,
            Chunk.content,
            Chunk.bridge_id,
            Bridge.name.label("bridge_name"),
            Chunk.lvl1,
            Chunk.lvl2,
            Chunk.bridge_binding_status,
            Chunk.source_id,
            Source.title.label("source_title"),
            Chunk.created_at,
        )
        .outerjoin(Bridge, Chunk.bridge_id == Bridge.id)
        .outerjoin(Source, Chunk.source_id == Source.id)
        .filter(Chunk.bridge_id == bridge_id)
    )

    total = query.count()
    offset = (page - 1) * page_size
    results = query.order_by(desc(Chunk.id)).offset(offset).limit(page_size).all()

    items = []
    for row in results:
        content = row.content
        content_preview = content[:80] + "..." if len(content) > 80 else content
        items.append(
            ChunkListItem(
                id=row.id,
                content_preview=content_preview,
                bridge_id=row.bridge_id,
                bridge_name=row.bridge_name,
                lvl1=row.lvl1,
                lvl2=row.lvl2,
                binding_status=row.bridge_binding_status,
                source_id=row.source_id,
                source_title=row.source_title,
                created_at=row.created_at,
            )
        )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/{target_id}/merge", response_model=BridgeDetail)
def merge_bridges(
    target_id: int, body: BridgeMergeRequest, db: Session = Depends(get_db)
) -> BridgeDetail:
    """Merge source bridge into target bridge.

    Migrates all chunks, links, and aliases from source to target, then deletes source.
    """
    if body.source_bridge_id == target_id:
        raise HTTPException(status_code=422, detail="Cannot merge a bridge into itself")

    target = db.query(Bridge).filter(Bridge.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target bridge not found")

    source = db.query(Bridge).filter(Bridge.id == body.source_bridge_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source bridge not found")

    # 1. Migrate primary chunks (bridge_id FK)
    db.query(Chunk).filter(Chunk.bridge_id == source.id).update(
        {Chunk.bridge_id: target.id}, synchronize_session=False
    )

    # 2. Migrate chunk_bridge_links (skip duplicates)
    existing_links = set(
        db.query(ChunkBridgeLink.chunk_id)
        .filter(ChunkBridgeLink.bridge_id == target.id)
        .scalars()
        .all()
    )
    source_links = (
        db.query(ChunkBridgeLink)
        .filter(ChunkBridgeLink.bridge_id == source.id)
        .all()
    )
    for link in source_links:
        if link.chunk_id in existing_links:
            db.delete(link)
        else:
            link.bridge_id = target.id

    # 3. Merge aliases (dedupe, preserve order)
    source_aliases = [s.strip() for s in (source.aliases or "").split(",") if s.strip()]
    source_aliases.append(source.name)
    target_aliases = [s.strip() for s in (target.aliases or "").split(",") if s.strip()]
    merged = list(dict.fromkeys(target_aliases + source_aliases))
    target.aliases = ", ".join(merged) if merged else None

    # 4. Delete source bridge
    db.delete(source)
    db.commit()

    # Return updated target
    return get_bridge(target_id, db)
