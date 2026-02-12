"""Stats API endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.v1.schemas.stats import (
    BindingDistribution,
    DashboardStats,
    Lvl1Distribution,
    RecentIngest,
)
from app.core.database import get_db
from app.models import Bridge, Chunk, Source

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)) -> DashboardStats:
    """Get aggregate statistics for dashboard."""
    # 1. Get totals
    chunk_count = db.query(func.count(Chunk.id)).scalar() or 0
    bridge_count = db.query(func.count(Bridge.id)).scalar() or 0
    source_count = db.query(func.count(Source.id)).scalar() or 0

    # 2. Get binding distribution
    binding_results = (
        db.query(Chunk.bridge_binding_status, func.count(Chunk.id))
        .group_by(Chunk.bridge_binding_status)
        .all()
    )
    binding_dict = {status: count for status, count in binding_results}
    binding_distribution = BindingDistribution(
        primary=binding_dict.get("primary", 0),
        ambiguous=binding_dict.get("ambiguous", 0),
        none=binding_dict.get("none", 0),
    )

    # 3. Compute ambiguous ratio
    ambiguous_count = binding_dict.get("ambiguous", 0)
    ambiguous_ratio = ambiguous_count / chunk_count if chunk_count > 0 else 0.0

    # 4. Get lvl1 distribution
    lvl1_results = (
        db.query(Chunk.lvl1, func.count(Chunk.id))
        .filter(Chunk.lvl1.isnot(None))
        .group_by(Chunk.lvl1)
        .order_by(desc(func.count(Chunk.id)))
        .all()
    )
    lvl1_distribution = [
        Lvl1Distribution(label=label, count=count) for label, count in lvl1_results
    ]

    # 5. Get recent ingests with chunk counts
    recent_sources = (
        db.query(
            Source.id,
            Source.title,
            func.count(Chunk.id).label("chunk_count"),
            Source.created_at,
        )
        .outerjoin(Chunk, Source.id == Chunk.source_id)
        .group_by(Source.id)
        .order_by(desc(Source.created_at))
        .limit(10)
        .all()
    )
    recent_ingests = [
        RecentIngest(
            source_id=source_id,
            title=title,
            chunk_count=chunk_count,
            created_at=created_at,
        )
        for source_id, title, chunk_count, created_at in recent_sources
    ]

    return DashboardStats(
        chunk_count=chunk_count,
        bridge_count=bridge_count,
        source_count=source_count,
        ambiguous_ratio=ambiguous_ratio,
        binding_distribution=binding_distribution,
        lvl1_distribution=lvl1_distribution,
        recent_ingests=recent_ingests,
    )
