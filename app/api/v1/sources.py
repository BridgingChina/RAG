"""Sources API endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.v1.schemas.common import PaginatedResponse
from app.api.v1.schemas.source import SourceDetail, SourceListItem
from app.core.database import get_db
from app.models import Chunk, Source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=PaginatedResponse[SourceListItem])
def list_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = None,
    type: str | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[SourceListItem]:
    """List all sources with optional search and type filter."""
    query = (
        db.query(
            Source.id,
            Source.type,
            Source.title,
            Source.url,
            Source.created_at,
            func.count(Chunk.id).label("chunk_count"),
        )
        .outerjoin(Chunk, Source.id == Chunk.source_id)
        .group_by(Source.id)
    )

    if q is not None:
        query = query.filter(Source.title.ilike(f"%{q}%"))
    if type is not None:
        query = query.filter(Source.type == type)

    total = query.count()
    offset = (page - 1) * page_size
    results = query.order_by(desc(Source.created_at)).offset(offset).limit(page_size).all()

    items = [
        SourceListItem(
            id=row.id,
            type=row.type,
            title=row.title,
            url=row.url,
            chunk_count=row.chunk_count,
            created_at=row.created_at,
        )
        for row in results
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: int, db: Session = Depends(get_db)) -> SourceDetail:
    """Get detailed information about a specific source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.source_id == source_id).scalar()

    return SourceDetail(
        id=source.id,
        type=source.type,
        title=source.title,
        url=source.url,
        file_path=source.file_path,
        accessed_at=source.accessed_at,
        chunk_count=chunk_count,
        created_at=source.created_at,
    )
