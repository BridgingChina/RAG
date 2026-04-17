"""Resolve a taxonomy path (lvl1, lvl2, lvl3) to the matching KnowledgePoint id.

Phase 3: queries KnowledgePoint directly by its own lvl1/lvl2/name columns —
no longer joins through taxonomy_nodes. This means the resolver works even
after the lvl3 rows are deleted from taxonomy_nodes.

Returns None if the chunk is not tagged to lvl3 or no matching KP exists.
"""
import uuid

from sqlalchemy.orm import Session

from app.models import KnowledgePoint


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
        .filter(
            KnowledgePoint.lvl1 == lvl1,
            KnowledgePoint.lvl2 == lvl2,
            KnowledgePoint.name == lvl3,
        )
        .first()
    )
    return row[0] if row else None
