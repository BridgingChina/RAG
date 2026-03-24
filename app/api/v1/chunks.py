"""Chunks CRUD API endpoints."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.chunk import (
    ChunkBatchRequest,
    ChunkBridgeLinkDetail,
    ChunkDetail,
    ChunkListItem,
    ChunkMergeRequest,
    ChunkSplitRequest,
    ChunkSplitResponse,
    ChunkUpdate,
)
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models import Bridge, Chunk, ChunkBridgeLink, Source, TaxonomyNode, User
from app.services.audit_service import AuditService
from app.services.chunk_editor import check_optimistic_lock, get_tokenizer

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("", response_model=PaginatedResponse[ChunkListItem])
def list_chunks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    bridge_id: UUID | None = None,
    lvl1: str | None = None,
    lvl2: str | None = None,
    lvl3: str | None = None,
    binding_status: str | None = None,
    source_id: UUID | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[ChunkListItem]:
    """List chunks with optional filters."""
    # Build base query
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
            Chunk.needs_reindex,
            Chunk.updated_at,
        )
        .outerjoin(Bridge, Chunk.bridge_id == Bridge.id)
        .outerjoin(Source, Chunk.source_id == Source.id)
    )

    # Apply filters
    if bridge_id is not None:
        query = query.filter(Chunk.bridge_id == bridge_id)
    if lvl1 is not None:
        query = query.filter(Chunk.lvl1 == lvl1)
    if lvl2 is not None:
        query = query.filter(Chunk.lvl2 == lvl2)
    if lvl3 is not None:
        query = query.filter(Chunk.lvl3 == lvl3)
    if binding_status is not None:
        query = query.filter(Chunk.bridge_binding_status == binding_status)
    if source_id is not None:
        query = query.filter(Chunk.source_id == source_id)
    if q is not None:
        query = query.filter(Chunk.content.ilike(f"%{q}%"))

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    results = query.order_by(desc(Chunk.id)).offset(offset).limit(page_size).all()

    # Build response items
    items = []
    for row in results:
        # Generate content preview
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
                needs_reindex=row.needs_reindex,
                updated_at=row.updated_at,
            )
        )

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{chunk_id}", response_model=ChunkDetail)
def get_chunk(chunk_id: UUID, db: Session = Depends(get_db)) -> ChunkDetail:
    """Get detailed information about a specific chunk."""
    # Fetch the chunk
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Fetch bridge name if bridge_id is set
    bridge_name = None
    if chunk.bridge_id:
        bridge = db.query(Bridge).filter(Bridge.id == chunk.bridge_id).first()
        if bridge:
            bridge_name = bridge.name

    # Fetch source title
    source_title = None
    source = db.query(Source).filter(Source.id == chunk.source_id).first()
    if source:
        source_title = source.title

    # Fetch bridge links with bridge names
    bridge_link_results = (
        db.query(ChunkBridgeLink, Bridge.name)
        .outerjoin(Bridge, ChunkBridgeLink.bridge_id == Bridge.id)
        .filter(ChunkBridgeLink.chunk_id == chunk_id)
        .all()
    )

    bridge_links = []
    for link, name in bridge_link_results:
        bridge_links.append(
            ChunkBridgeLinkDetail(
                id=link.id,
                bridge_id=link.bridge_id,
                bridge_name=name,
                role=link.role,
                confidence=link.confidence,
                method=link.method,
            )
        )

    return ChunkDetail(
        id=chunk.id,
        content=chunk.content,
        contextual_text=chunk.contextual_text,
        search_text=chunk.search_text,
        section_title=chunk.section_title,
        page_range=chunk.page_range,
        lvl1=chunk.lvl1,
        lvl2=chunk.lvl2,
        lvl3=chunk.lvl3,
        bridge_id=chunk.bridge_id,
        bridge_name=bridge_name,
        binding_status=chunk.bridge_binding_status,
        source_id=chunk.source_id,
        source_title=source_title,
        created_at=chunk.created_at,
        bridge_links=bridge_links,
        needs_reindex=chunk.needs_reindex,
        updated_at=chunk.updated_at,
    )


@router.put("/{chunk_id}", response_model=ChunkDetail)
def update_chunk(
    chunk_id: UUID,
    body: ChunkUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChunkDetail:
    """Update a chunk's metadata."""
    # Fetch the chunk
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Optimistic lock check
    check_optimistic_lock(chunk, body.expected_updated_at)

    # Get update data, excluding unset fields
    update_data = body.model_dump(exclude_unset=True)
    update_data.pop("expected_updated_at", None)

    # Validate taxonomy path exists if any lvl field is being set
    new_lvl1 = update_data.get("lvl1", chunk.lvl1)
    new_lvl2 = update_data.get("lvl2", chunk.lvl2)
    new_lvl3 = update_data.get("lvl3", chunk.lvl3)
    if any(k in update_data for k in ("lvl1", "lvl2", "lvl3")) and new_lvl1:
        if new_lvl3 and not new_lvl2:
            raise HTTPException(status_code=422, detail="lvl3 requires lvl2")
        node_q = db.query(TaxonomyNode).filter(TaxonomyNode.lvl1 == new_lvl1)
        if new_lvl2:
            node_q = node_q.filter(TaxonomyNode.lvl2 == new_lvl2)
        else:
            node_q = node_q.filter(TaxonomyNode.lvl2.is_(None))
        if new_lvl3:
            node_q = node_q.filter(TaxonomyNode.lvl3 == new_lvl3)
        else:
            node_q = node_q.filter(TaxonomyNode.lvl3.is_(None))
        if not node_q.first():
            raise HTTPException(
                status_code=422,
                detail=f"Taxonomy path not found: {new_lvl1}/{new_lvl2 or ''}/{new_lvl3 or ''}",
            )

    # Validate bridge_id exists if being set
    if "bridge_id" in update_data and update_data["bridge_id"] is not None:
        bridge_exists = db.query(Bridge).filter(
            Bridge.id == update_data["bridge_id"]
        ).first()
        if not bridge_exists:
            raise HTTPException(
                status_code=422,
                detail=f"Bridge {update_data['bridge_id']} not found",
            )

    # Map binding_status to bridge_binding_status
    if "binding_status" in update_data:
        update_data["bridge_binding_status"] = update_data.pop("binding_status")

    # Handle content update (requires search_text + tsv recomputation)
    if "content" in update_data:
        from app.services.chunk_editor import update_chunk_content
        tokenizer = get_tokenizer()
        update_chunk_content(
            db=db, chunk=chunk, new_content=update_data.pop("content"), tokenizer=tokenizer,
        )

    # Handle bridge_links replacement
    if "bridge_links" in update_data:
        from app.services.chunk_editor import replace_bridge_links
        bridge_links_data = update_data.pop("bridge_links")
        if bridge_links_data is not None:
            # Validate all bridge_ids exist in a single query
            requested_ids = {bl["bridge_id"] for bl in bridge_links_data}
            existing_ids = {
                row.id
                for row in db.query(Bridge.id).filter(Bridge.id.in_(requested_ids)).all()
            }
            missing = requested_ids - existing_ids
            if missing:
                raise HTTPException(status_code=422, detail=f"Bridges not found: {sorted(missing)}")
            replace_bridge_links(db=db, chunk=chunk, links=bridge_links_data)

    # Apply remaining updates (lvl1/2/3, bridge_id, bridge_binding_status)
    for key, value in update_data.items():
        setattr(chunk, key, value)

    db.commit()
    db.refresh(chunk)

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="chunk",
        user_id=current_user.id,
        resource_id=str(chunk_id),
        ip_address=get_client_ip(request),
    )
    db.commit()

    # Return full detail using the get endpoint
    return get_chunk(chunk_id, db)


@router.delete("/{chunk_id}", status_code=204)
def delete_chunk(
    chunk_id: UUID,
    request: Request,
    expected_updated_at: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a chunk and its bridge links."""
    # Fetch the chunk
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Optimistic lock check
    check_optimistic_lock(chunk, expected_updated_at)

    # Audit log before delete so flush happens before the row is removed
    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="chunk",
        user_id=current_user.id,
        resource_id=str(chunk_id),
        ip_address=get_client_ip(request),
    )

    # Delete associated bridge links first
    db.query(ChunkBridgeLink).filter(ChunkBridgeLink.chunk_id == chunk_id).delete()

    # Delete the chunk
    db.delete(chunk)
    db.commit()


@router.post("/merge", response_model=ChunkDetail)
def merge_chunks_endpoint(
    body: ChunkMergeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChunkDetail:
    """Merge multiple chunks into one."""
    from app.services.chunk_editor import merge_chunks as do_merge

    try:
        merged = do_merge(db=db, chunk_ids=body.chunk_ids, tokenizer=get_tokenizer())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    AuditService.log(
        db,
        action="merge",
        resource_type="chunk",
        user_id=current_user.id,
        resource_id=str(merged.id),
        detail={"merged_chunk_ids": body.chunk_ids},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return get_chunk(merged.id, db)


@router.patch("/batch", status_code=200)
def batch_chunks(
    body: ChunkBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Batch update or delete chunks."""
    # Validate all chunk_ids exist
    existing = db.query(Chunk.id).filter(Chunk.id.in_(body.chunk_ids)).all()
    existing_ids = {row.id for row in existing}
    missing = set(body.chunk_ids) - existing_ids
    if missing:
        raise HTTPException(status_code=400, detail=f"Chunks not found: {sorted(missing)}")

    if body.action == "delete":
        db.query(ChunkBridgeLink).filter(
            ChunkBridgeLink.chunk_id.in_(body.chunk_ids)
        ).delete()
        count = db.query(Chunk).filter(Chunk.id.in_(body.chunk_ids)).delete()
        db.flush()

        AuditService.log(
            db,
            action="batch_delete",
            resource_type="chunk",
            user_id=current_user.id,
            detail={"chunk_ids": body.chunk_ids},
            ip_address=get_client_ip(request),
        )
        db.commit()
        return {"deleted": count}

    elif body.action == "update":
        if not body.updates:
            raise HTTPException(status_code=400, detail="updates required for action=update")

        update_data = body.updates.model_dump(exclude_unset=True)
        if "binding_status" in update_data:
            update_data["bridge_binding_status"] = update_data.pop("binding_status")

        # Validate bridge_id if present
        if "bridge_id" in update_data and update_data["bridge_id"] is not None:
            if not db.query(Bridge).filter(Bridge.id == update_data["bridge_id"]).first():
                raise HTTPException(
                    status_code=422, detail=f"Bridge {update_data['bridge_id']} not found"
                )

        # Log audit detail before adding non-serializable func.now()
        audit_updates = dict(update_data)

        update_data["updated_at"] = func.now()
        count = db.query(Chunk).filter(Chunk.id.in_(body.chunk_ids)).update(
            update_data, synchronize_session="fetch"
        )
        db.flush()

        AuditService.log(
            db,
            action="batch_update",
            resource_type="chunk",
            user_id=current_user.id,
            detail={"chunk_ids": body.chunk_ids, "updates": audit_updates},
            ip_address=get_client_ip(request),
        )
        db.commit()
        return {"updated": count}


@router.post("/{chunk_id}/split", response_model=ChunkSplitResponse)
def split_chunk_endpoint(
    chunk_id: UUID,
    body: ChunkSplitRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChunkSplitResponse:
    """Split a chunk at the given character position."""
    from app.services.chunk_editor import split_chunk as do_split

    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Optimistic lock check
    check_optimistic_lock(chunk, body.expected_updated_at)

    try:
        new_chunks = do_split(
            db=db, chunk=chunk, position=body.position, tokenizer=get_tokenizer(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    AuditService.log(
        db,
        action="split",
        resource_type="chunk",
        user_id=current_user.id,
        resource_id=str(chunk_id),
        detail={"new_chunk_ids": [c.id for c in new_chunks]},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return ChunkSplitResponse(chunks=[get_chunk(c.id, db) for c in new_chunks])
