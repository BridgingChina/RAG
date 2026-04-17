"""Resolve a taxonomy path (lvl1, lvl2, lvl3) to the matching KnowledgePoint id.

Transitional helper for the lvl3-KP merge refactor (Phase 1).

Ingest/tagging/split writes the lvl1/lvl2/lvl3 string tags to a chunk; this
helper looks up the same-name KnowledgePoint via the taxonomy node path and
returns its id so callers can populate the new `chunks.knowledge_point_id`
FK alongside the legacy string columns (double-write).

Returns None if the chunk is not tagged to lvl3 or no matching KP exists.
"""
import uuid

from sqlalchemy.orm import Session

from app.models import KnowledgePoint, TaxonomyNode


def resolve_knowledge_point_id(
    db: Session,
    lvl1: str | None,
    lvl2: str | None,
    lvl3: str | None,
) -> uuid.UUID | None:
    if not lvl3:
        return None
    row = (
        db.query(KnowledgePoint.id)
        .join(TaxonomyNode, KnowledgePoint.taxonomy_node_id == TaxonomyNode.id)
        .filter(
            TaxonomyNode.lvl1 == lvl1,
            TaxonomyNode.lvl2 == lvl2,
            TaxonomyNode.lvl3 == lvl3,
        )
        .first()
    )
    return row[0] if row else None
