"""Mobile API: Unified search endpoint."""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.mobile.v1.schemas.common import MobileMeta, MobilePaginatedResponse
from app.api.mobile.v1.schemas.search import SearchResultItem
from app.core.database import get_db
from app.models.bridge import Bridge
from app.models.knowledge_point import KnowledgePoint
from app.models.taxonomy import TaxonomyNode

router = APIRouter()


def _escape_like(s: str) -> str:
    """Escape special characters for SQL LIKE/ILIKE patterns."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _highlight(text: str, keyword: str) -> str:
    """Wrap keyword matches in <em> tags (case-insensitive)."""
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    return pattern.sub(lambda m: f"<em>{m.group()}</em>", text)


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
    results: list[SearchResultItem] = []

    # --- Bridge search ---
    if type in ("all", "bridge"):
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

        for b in stmt.all():
            highlight_text = _highlight(b.name, q)
            if b.aliases and q.lower() in b.aliases.lower():
                highlight_text = _highlight(b.aliases, q)
            results.append(
                SearchResultItem(
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
            )

    # --- Knowledge point search ---
    if type in ("all", "knowledge_point"):
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

        for kp in stmt.all():
            highlight_text = _highlight(kp.name, q)
            if kp.aliases and q.lower() in kp.aliases.lower():
                highlight_text = _highlight(kp.aliases, q)
            results.append(
                SearchResultItem(
                    type="knowledge_point",
                    id=kp.id,
                    name=kp.name,
                    aliases=kp.aliases,
                    highlight=highlight_text,
                )
            )

    # --- Pagination ---
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    page_results = results[start:end]

    return MobilePaginatedResponse(
        data=page_results,
        meta=MobileMeta(total=total, page=page, page_size=page_size),
    )
