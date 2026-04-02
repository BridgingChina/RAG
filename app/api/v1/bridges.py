"""Bridges CRUD API endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.bridge import (
    BatchGeocodeRequest,
    BatchGeocodeResponse,
    BridgeCreate,
    BridgeDetail,
    BridgeListItem,
    BridgeMergePreview,
    BridgeMergeRequest,
    BridgeUpdate,
    CSVImportResponse,
)
from app.api.v1.schemas.bridge_image import (
    BridgeImageResponse,
    ImageConfirmRequest,
    ImagePresignRequest,
    ImagePresignResponse,
    ImageReorderRequest,
)
from app.api.v1.schemas.chunk import ChunkListItem
from app.api.v1.schemas.common import PaginatedResponse
from app.api.v1.pagination import paginate
from app.core.database import get_db
from app.models import Bridge, Chunk, ChunkBridgeLink, Source, User
from app.services.audit_service import AuditService
from app.services.bridge_image_service import BridgeImageService
from app.services.geocode_service import GeocodeService
from app.services.r2_storage import R2StorageService

router = APIRouter(prefix="/bridges", tags=["bridges"])


def _get_r2() -> R2StorageService:
    if not R2StorageService.is_configured():
        raise HTTPException(
            status_code=503,
            detail="R2 storage is not configured",
        )
    return R2StorageService()


def _get_image_service(r2: R2StorageService = Depends(_get_r2)) -> BridgeImageService:
    return BridgeImageService(r2)


def _ensure_bridge(db: Session, bridge_id: UUID) -> Bridge:
    bridge = db.query(Bridge).filter(Bridge.id == bridge_id).first()
    if not bridge:
        raise HTTPException(status_code=404, detail="Bridge not found")
    return bridge


# ── Bridge image endpoints (must be before /{bridge_id} parametric route) ──


@router.post(
    "/{bridge_id}/images/presign",
    response_model=ImagePresignResponse,
    tags=["bridge-images"],
)
def presign_image_upload(
    bridge_id: UUID,
    body: ImagePresignRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: BridgeImageService = Depends(_get_image_service),
) -> ImagePresignResponse:
    """Generate presigned URL for uploading a bridge image to R2."""
    _ensure_bridge(db, bridge_id)
    image, upload_url = svc.presign_upload(db, bridge_id, body.file_name, body.content_type)

    AuditService.log(
        db,
        action=AuditService.CREATE,
        resource_type="bridge_image",
        user_id=current_user.id,
        resource_id=str(image.id),
        detail={"bridge_id": str(bridge_id), "r2_key": image.r2_key},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return ImagePresignResponse(
        image_id=image.id,
        upload_url=upload_url,
        r2_key=image.r2_key,
    )


@router.post(
    "/{bridge_id}/images",
    response_model=BridgeImageResponse,
    tags=["bridge-images"],
)
def confirm_image_upload(
    bridge_id: UUID,
    body: ImageConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: BridgeImageService = Depends(_get_image_service),
) -> BridgeImageResponse:
    """Confirm image upload and optionally set caption/type."""
    _ensure_bridge(db, bridge_id)
    try:
        image = svc.confirm_upload(db, body.image_id, bridge_id, body.caption, body.type)
    except ValueError:
        raise HTTPException(status_code=404, detail="Image not found")

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="bridge_image",
        user_id=current_user.id,
        resource_id=str(image.id),
        detail={"bridge_id": str(bridge_id), "caption": body.caption, "type": body.type},
        ip_address=get_client_ip(request),
    )
    db.commit()

    return BridgeImageResponse(
        id=image.id,
        bridge_id=image.bridge_id,
        url=BridgeImageService.get_public_url(image.r2_key),
        caption=image.caption,
        type=image.type,
        order_index=image.order_index,
        created_at=image.created_at,
    )


@router.get(
    "/{bridge_id}/images",
    response_model=list[BridgeImageResponse],
    tags=["bridge-images"],
)
def list_bridge_images(
    bridge_id: UUID,
    db: Session = Depends(get_db),
    svc: BridgeImageService = Depends(_get_image_service),
) -> list[BridgeImageResponse]:
    """List all images for a bridge, ordered by order_index."""
    _ensure_bridge(db, bridge_id)
    images = svc.list_images(db, bridge_id)
    return [
        BridgeImageResponse(
            id=img.id,
            bridge_id=img.bridge_id,
            url=BridgeImageService.get_public_url(img.r2_key),
            caption=img.caption,
            type=img.type,
            order_index=img.order_index,
            created_at=img.created_at,
        )
        for img in images
    ]


@router.put(
    "/{bridge_id}/images/reorder",
    status_code=204,
    tags=["bridge-images"],
)
def reorder_bridge_images(
    bridge_id: UUID,
    body: ImageReorderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: BridgeImageService = Depends(_get_image_service),
) -> None:
    """Reorder images for a bridge."""
    _ensure_bridge(db, bridge_id)
    svc.reorder(db, bridge_id, body.image_ids)

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="bridge_image",
        user_id=current_user.id,
        resource_id=str(bridge_id),
        detail={"action": "reorder", "image_ids": [str(i) for i in body.image_ids]},
        ip_address=get_client_ip(request),
    )
    db.commit()


@router.delete(
    "/{bridge_id}/images/{image_id}",
    status_code=204,
    tags=["bridge-images"],
)
def delete_bridge_image(
    bridge_id: UUID,
    image_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    svc: BridgeImageService = Depends(_get_image_service),
) -> None:
    """Delete a bridge image (record + R2 object)."""
    _ensure_bridge(db, bridge_id)

    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="bridge_image",
        user_id=current_user.id,
        resource_id=str(image_id),
        detail={"bridge_id": str(bridge_id)},
        ip_address=get_client_ip(request),
    )

    try:
        svc.delete(db, image_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Image not found")

    db.commit()


# ── Geocode endpoints (must be before /{bridge_id} parametric route) ──


@router.post("/batch-geocode", response_model=BatchGeocodeResponse)
async def batch_geocode(
    body: BatchGeocodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchGeocodeResponse:
    """Batch geocode bridges using Amap API. Blocking — awaits all geocoding inline."""
    svc = GeocodeService()
    result = await svc.batch_geocode(db, body.bridge_ids)

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="bridge",
        user_id=current_user.id,
        detail={
            "action": "batch_geocode",
            "total": result["total"],
            "success": result["success"],
            "failed": result["failed"],
        },
        ip_address=get_client_ip(request),
    )
    db.commit()

    return BatchGeocodeResponse(
        total=result["total"],
        success=result["success"],
        failed=result["failed"],
    )


@router.post("/import-coordinates", response_model=CSVImportResponse)
async def import_coordinates(
    file: UploadFile,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CSVImportResponse:
    """Import bridge coordinates from a CSV file (columns: name, latitude, longitude)."""
    content = await file.read()
    csv_content = content.decode("utf-8-sig")

    svc = GeocodeService()
    result = svc.import_from_csv(db, csv_content)

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="bridge",
        user_id=current_user.id,
        detail={
            "action": "import_coordinates",
            "matched": result["matched"],
            "unmatched": result["unmatched"],
        },
        ip_address=get_client_ip(request),
    )
    db.commit()

    return CSVImportResponse(
        matched=result["matched"],
        unmatched=result["unmatched"],
    )


# ── Bridge CRUD endpoints ──


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
            Bridge.region,
            Bridge.latitude,
            Bridge.longitude,
            Bridge.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Bridge.id == Chunk.bridge_id)
        .group_by(Bridge.id)
    )

    # Apply search filter
    if q is not None:
        query = query.filter(Bridge.name.ilike(f"%{q}%"))

    return paginate(
        query.order_by(Bridge.name),
        page,
        page_size,
        lambda row: BridgeListItem(
            id=row.id,
            name=row.name,
            aliases=row.aliases,
            bridge_type=row.bridge_type,
            material=row.material,
            era=row.era,
            region=row.region,
            latitude=row.latitude,
            longitude=row.longitude,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
        ),
    )


@router.get("/{bridge_id}", response_model=BridgeDetail)
def get_bridge(bridge_id: UUID, db: Session = Depends(get_db)) -> BridgeDetail:
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
        region=bridge.region,
        latitude=bridge.latitude,
        longitude=bridge.longitude,
        function=bridge.function,
        summary=bridge.summary,
        chunk_count=chunk_count,
        created_at=bridge.created_at,
    )


@router.post("", response_model=BridgeDetail, status_code=201)
def create_bridge(
    body: BridgeCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BridgeDetail:
    """Create a new bridge."""
    # Check for duplicate name
    existing = db.query(Bridge).filter(Bridge.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Bridge with name '{body.name}' already exists")

    # Create the bridge
    bridge = Bridge(**body.model_dump())
    db.add(bridge)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Bridge with name '{body.name}' already exists")

    AuditService.log(
        db,
        action=AuditService.CREATE,
        resource_type="bridge",
        user_id=current_user.id,
        resource_id=str(bridge.id),
        ip_address=get_client_ip(request),
    )
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
        region=bridge.region,
        latitude=bridge.latitude,
        longitude=bridge.longitude,
        function=bridge.function,
        summary=bridge.summary,
        chunk_count=0,
        created_at=bridge.created_at,
    )


@router.put("/{bridge_id}", response_model=BridgeDetail)
def update_bridge(
    bridge_id: UUID,
    body: BridgeUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
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

    db.flush()

    AuditService.log(
        db,
        action=AuditService.UPDATE,
        resource_type="bridge",
        user_id=current_user.id,
        resource_id=str(bridge_id),
        ip_address=get_client_ip(request),
    )
    db.commit()
    db.refresh(bridge)

    # Return full detail using the get endpoint
    return get_bridge(bridge_id, db)


@router.delete("/{bridge_id}", status_code=204)
def delete_bridge(
    bridge_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
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

    # Audit log before delete so flush happens before the row is removed
    AuditService.log(
        db,
        action=AuditService.DELETE,
        resource_type="bridge",
        user_id=current_user.id,
        resource_id=str(bridge_id),
        ip_address=get_client_ip(request),
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
    bridge_id: UUID,
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
            Chunk.needs_reindex,
            Chunk.updated_at,
        )
        .outerjoin(Bridge, Chunk.bridge_id == Bridge.id)
        .outerjoin(Source, Chunk.source_id == Source.id)
        .filter(Chunk.bridge_id == bridge_id)
    )

    def _to_chunk_list_item(row):
        content = row.content
        content_preview = content[:80] + "..." if len(content) > 80 else content
        return ChunkListItem(
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

    return paginate(query.order_by(desc(Chunk.id)), page, page_size, _to_chunk_list_item)


@router.post("/{target_id}/merge", response_model=BridgeDetail | BridgeMergePreview)
def merge_bridges(
    target_id: UUID,
    body: BridgeMergeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    dry_run: bool = Query(False),
) -> BridgeDetail | BridgeMergePreview:
    """Merge source bridge into target bridge.

    When dry_run=true, returns a preview of what would happen without executing.
    When dry_run=false (default), migrates all chunks, links, and aliases from
    source to target, then deletes source.
    """
    if body.source_bridge_id == target_id:
        raise HTTPException(status_code=422, detail="Cannot merge a bridge into itself")

    target = db.query(Bridge).filter(Bridge.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target bridge not found")

    source = db.query(Bridge).filter(Bridge.id == body.source_bridge_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source bridge not found")

    # Compute aliases that would be added (needed for both dry_run and actual merge)
    source_aliases = [s.strip() for s in (source.aliases or "").split(",") if s.strip()]
    source_aliases.append(source.name)
    target_aliases = [s.strip() for s in (target.aliases or "").split(",") if s.strip()]
    new_aliases = [a for a in source_aliases if a not in target_aliases]

    if dry_run:
        # Count chunks that would move
        chunks_to_move = (
            db.query(func.count(Chunk.id))
            .filter(Chunk.bridge_id == source.id)
            .scalar()
        )

        # Count links that would move (excluding duplicates)
        existing_link_chunks = {
            row[0]
            for row in db.query(ChunkBridgeLink.chunk_id)
            .filter(ChunkBridgeLink.bridge_id == target.id)
            .all()
        }
        source_link_count = (
            db.query(func.count(ChunkBridgeLink.id))
            .filter(ChunkBridgeLink.bridge_id == source.id)
            .scalar()
        )
        duplicate_links = (
            db.query(func.count(ChunkBridgeLink.id))
            .filter(
                ChunkBridgeLink.bridge_id == source.id,
                ChunkBridgeLink.chunk_id.in_(existing_link_chunks),
            )
            .scalar()
            if existing_link_chunks
            else 0
        )

        return BridgeMergePreview(
            source_bridge_id=source.id,
            source_bridge_name=source.name,
            target_bridge_id=target.id,
            target_bridge_name=target.name,
            chunks_to_move=chunks_to_move,
            links_to_move=source_link_count - duplicate_links,
            aliases_to_add=new_aliases,
        )

    # 1. Migrate primary chunks (bridge_id FK)
    db.query(Chunk).filter(Chunk.bridge_id == source.id).update(
        {Chunk.bridge_id: target.id}, synchronize_session=False
    )

    # 2. Migrate chunk_bridge_links (skip duplicates)
    existing_links = {
        row[0]
        for row in db.query(ChunkBridgeLink.chunk_id)
        .filter(ChunkBridgeLink.bridge_id == target.id)
        .all()
    }
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
    merged = list(dict.fromkeys(target_aliases + source_aliases))
    target.aliases = ", ".join(merged) if merged else None

    # 4. Delete source bridge
    db.delete(source)
    db.flush()

    AuditService.log(
        db,
        action=AuditService.MERGE,
        resource_type="bridge",
        user_id=current_user.id,
        resource_id=str(target_id),
        detail={"source_bridge_id": str(body.source_bridge_id)},
        ip_address=get_client_ip(request),
    )
    db.commit()

    # Return updated target
    return get_bridge(target_id, db)
