"""Mobile API: Unified search endpoint."""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse
from app.api.mobile.v1.schemas.search import SearchResultItem
from app.api.mobile.v1.utils import escape_like as _escape_like
from app.core.database import get_db
from app.models.bridge import Bridge
from app.models.knowledge_point import KnowledgePoint
from app.models.taxonomy import TaxonomyNode

router = APIRouter()


def _highlight(text: str, keyword: str) -> str:
    """Wrap keyword matches in <em> tags (case-insensitive)."""
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    return pattern.sub(lambda m: f"<em>{m.group()}</em>", text)


def _build_bridge_query(db: Session, like_pattern: str, bridge_type: str | None, era: str | None, region: str | None):
    """Build the bridge search query with filters."""
    stmt = db.query(Bridge).filter(
        or_(
            Bridge.name.ilike(like_pattern),
            Bridge.aliases.ilike(like_pattern),
        )
    )
    if bridge_type:
        stmt = stmt.filter(Bridge.bridge_type == bridge_type)
    if era:
        stmt = stmt.filter(Bridge.era == era)
    if region:
        stmt = stmt.filter(Bridge.region == region)
    return stmt


def _build_kp_query(db: Session, like_pattern: str, line: str | None, category: str | None):
    """Build the knowledge point search query with filters."""
    stmt = db.query(KnowledgePoint).filter(
        or_(
            KnowledgePoint.name.ilike(like_pattern),
            KnowledgePoint.aliases.ilike(like_pattern),
        )
    )
    if line:
        stmt = stmt.join(TaxonomyNode, KnowledgePoint.taxonomy_node_id == TaxonomyNode.id).filter(
            TaxonomyNode.lvl1 == line,
        )
    if category:
        if not line:
            stmt = stmt.join(TaxonomyNode, KnowledgePoint.taxonomy_node_id == TaxonomyNode.id)
        stmt = stmt.filter(TaxonomyNode.lvl2 == category)
    return stmt


def _bridge_to_item(b: Bridge, q: str) -> SearchResultItem:
    highlight_text = _highlight(b.name, q)
    if b.aliases and q.lower() in b.aliases.lower():
        highlight_text = _highlight(b.aliases, q)
    return SearchResultItem(
        type="bridge",
        id=b.id,
        name=b.name,
        aliases=b.aliases,
        highlight=highlight_text,
        bridge_type=b.bridge_type,
        era=b.era,
        region=b.region,
        latitude=b.latitude,
        longitude=b.longitude,
    )


def _kp_to_item(kp: KnowledgePoint, q: str) -> SearchResultItem:
    highlight_text = _highlight(kp.name, q)
    if kp.aliases and q.lower() in kp.aliases.lower():
        highlight_text = _highlight(kp.aliases, q)
    return SearchResultItem(
        type="knowledge_point",
        id=kp.id,
        name=kp.name,
        aliases=kp.aliases,
        highlight=highlight_text,
    )


@router.get("/search")
def search(
    q: str = Query(..., min_length=1),
    type: str = Query(default="all"),
    bridge_type: str | None = Query(default=None),
    era: str | None = Query(default=None),
    region: str | None = Query(default=None),
    line: str | None = Query(default=None),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> MobilePaginatedResponse[list[SearchResultItem]]:
    """Unified search across bridges and knowledge points."""
    like_pattern = f"%{_escape_like(q)}%"
    offset = (page - 1) * page_size

    # --- Single-type search: use SQL LIMIT/OFFSET directly ---
    if type == "bridge":
        bridge_q = _build_bridge_query(db, like_pattern, bridge_type, era, region)
        total = bridge_q.count()
        bridges = bridge_q.order_by(Bridge.name).offset(offset).limit(page_size).all()
        results = [_bridge_to_item(b, q) for b in bridges]
        return MobilePaginatedResponse(
            data=results,
            meta=MobileMeta(total=total, page=page, page_size=page_size),
        )

    if type == "knowledge_point":
        kp_q = _build_kp_query(db, like_pattern, line, category)
        total = kp_q.count()
        kps = kp_q.order_by(KnowledgePoint.name).offset(offset).limit(page_size).all()
        results = [_kp_to_item(kp, q) for kp in kps]
        return MobilePaginatedResponse(
            data=results,
            meta=MobileMeta(total=total, page=page, page_size=page_size),
        )

    # --- type="all": interleaved strategy ---
    # Each type gets half the page, surplus fills from whichever has more.
    bridge_q = _build_bridge_query(db, like_pattern, bridge_type, era, region)
    kp_q = _build_kp_query(db, like_pattern, line, category)

    bridge_total = bridge_q.count()
    kp_total = kp_q.count()
    total = bridge_total + kp_total

    half = page_size // 2
    # Each type gets at least half, but if one type has fewer, the other gets more
    b_limit = min(half, bridge_total - offset) if offset < bridge_total else 0
    b_limit = max(b_limit, 0)
    k_limit = page_size - b_limit

    # Cap knowledge point limit by what's actually available
    kp_avail = max(kp_total - offset, 0) if offset < kp_total else 0
    if k_limit > kp_avail:
        # Give surplus back to bridges
        extra = min(k_limit - kp_avail, max(bridge_total - offset - b_limit, 0))
        b_limit += extra
        k_limit = kp_avail

    results: list[SearchResultItem] = []
    if b_limit > 0:
        bridges = bridge_q.order_by(Bridge.name).offset(offset).limit(b_limit).all()
        results.extend(_bridge_to_item(b, q) for b in bridges)
    if k_limit > 0:
        kps = kp_q.order_by(KnowledgePoint.name).offset(offset).limit(k_limit).all()
        results.extend(_kp_to_item(kp, q) for kp in kps)

    return MobilePaginatedResponse(
        data=results,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
