"""Chunks CRUD API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.chunk import (
    ChunkBridgeLinkDetail,
    ChunkDetail,
    ChunkListItem,
    ChunkUpdate,
)
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models import Bridge, Chunk, ChunkBridgeLink, Source, TaxonomyNode, User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/chunks", tags=["chunks"])


@router.get("", response_model=PaginatedResponse[ChunkListItem])
def list_chunks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    bridge_id: int | None = None,
    lvl1: str | None = None,
    lvl2: str | None = None,
    lvl3: str | None = None,
    binding_status: str | None = None,
    source_id: int | None = None,
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
def get_chunk(chunk_id: int, db: Session = Depends(get_db)) -> ChunkDetail:
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
    )


@router.put("/{chunk_id}", response_model=ChunkDetail)
def update_chunk(
    chunk_id: int,
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

    # Get update data, excluding unset fields
    update_data = body.model_dump(exclude_unset=True)

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
        from app.services.tokenizer import Tokenizer, default_user_dict_path
        tokenizer = Tokenizer(user_dict_path=default_user_dict_path())
        update_chunk_content(
            db=db, chunk=chunk, new_content=update_data.pop("content"), tokenizer=tokenizer,
        )

    # Handle section_title separately (simple field update)
    if "section_title" in update_data:
        chunk.section_title = update_data.pop("section_title")

    # Handle bridge_links replacement (placeholder for Task 4)
    if "bridge_links" in update_data:
        update_data.pop("bridge_links")  # Will be implemented in Task 4

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
    chunk_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a chunk and its bridge links."""
    # Fetch the chunk
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

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
