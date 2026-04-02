"""Bridge name resolver — matches bridge names in question text.

Extracted from app/api/v1/ask.py so both admin and mobile API layers
can use it without cross-layer imports.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bridge

logger = logging.getLogger(__name__)


def resolve_bridge_from_question(db: Session, question: str) -> uuid.UUID | None:
    """Try to find a bridge whose name appears in the question text.

    Matches the longest bridge name first to avoid partial matches
    (e.g. "碧波廊桥" should match before "碧波").
    """
    rows = db.execute(
        select(Bridge.id, Bridge.name).where(Bridge.name.isnot(None))
    ).all()
    # Sort by name length descending so longest match wins
    candidates = sorted(rows, key=lambda r: len(r.name), reverse=True)
    for row in candidates:
        if row.name and row.name in question:
            return row.id
    return None
