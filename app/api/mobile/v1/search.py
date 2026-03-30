"""Mobile API: Unified search endpoint."""
import html
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
    escaped = html.escape(text)
    escaped_kw = html.escape(keyword)
    pattern = re.compile(re.escape(escaped_kw), re.IGNORECASE)
    return pattern.sub(lambda m: f"<em>{m.group()}</em>", escaped)


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
    type: str = Query(default="all", pattern="^(all|bridge|knowledge_point)$"),
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

    # --- type="all": merge both types, paginate combined list ---
    # Data volume is small (<1000 bridges + KPs), so in-memory merge is fine.
    bridge_q = _build_bridge_query(db, like_pattern, bridge_type, era, region)
    kp_q = _build_kp_query(db, like_pattern, line, category)

    bridge_total = bridge_q.count()
    kp_total = kp_q.count()
    total = bridge_total + kp_total

    # Fetch only what we need: skip via SQL where possible
    results: list[SearchResultItem] = []

    if offset < bridge_total:
        # Page starts in bridges
        b_items = bridge_q.order_by(Bridge.name).offset(offset).limit(page_size).all()
        results.extend(_bridge_to_item(b, q) for b in b_items)
        remaining = page_size - len(results)
        if remaining > 0:
            # Fill rest from KPs (from the start)
            kp_items = kp_q.order_by(KnowledgePoint.name).limit(remaining).all()
            results.extend(_kp_to_item(kp, q) for kp in kp_items)
    else:
        # Page is entirely in KPs
        kp_offset = offset - bridge_total
        kp_items = kp_q.order_by(KnowledgePoint.name).offset(kp_offset).limit(page_size).all()
        results.extend(_kp_to_item(kp, q) for kp in kp_items)

    return MobilePaginatedResponse(
        data=results,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
