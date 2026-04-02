"""Bridge name resolver — matches bridge names in question text.

Extracted from app/api/v1/ask.py so both admin and mobile API layers
can use it without cross-layer imports.

Uses a module-level TTL cache (5 min) to avoid full table scan per request.
Thread-safe: guarded by _bridge_cache_lock (sync endpoints run in threadpool).
"""

import logging
import threading
import time
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bridge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bridge name cache for resolve_bridge_from_question
# Avoids SELECT * FROM bridges on every /ask request.
# Structure: {"data": [(id, name), ...], "ts": monotonic_timestamp}
# TTL: 5 minutes.  Invalidate explicitly via invalidate_bridge_cache().
# ---------------------------------------------------------------------------
_bridge_cache: dict[str, object] = {}
_bridge_cache_lock = threading.Lock()
_BRIDGE_CACHE_TTL = 300  # seconds


def _get_bridge_candidates(db: Session) -> list[tuple[uuid.UUID, str]]:
    """Return cached (id, name) pairs sorted by name length descending."""
    now = time.monotonic()
    with _bridge_cache_lock:
        cached_ts = _bridge_cache.get("ts")
        if cached_ts is not None and now - cached_ts < _BRIDGE_CACHE_TTL:
            return _bridge_cache["data"]  # type: ignore[return-value]

    rows = db.execute(
        select(Bridge.id, Bridge.name).where(Bridge.name.isnot(None))
    ).all()
    # Sort by name length descending so longest match wins
    candidates = sorted(
        [(row.id, row.name) for row in rows],
        key=lambda r: len(r[1]),
        reverse=True,
    )
    with _bridge_cache_lock:
        _bridge_cache["data"] = candidates
        _bridge_cache["ts"] = now
    logger.debug("Refreshed bridge name cache: %d entries", len(candidates))
    return candidates


def invalidate_bridge_cache() -> None:
    """Clear the bridge name cache (call after bridge create/update/delete)."""
    with _bridge_cache_lock:
        _bridge_cache.clear()


def resolve_bridge_from_question(db: Session, question: str) -> uuid.UUID | None:
    """Try to find a bridge whose name appears in the question text.

    Matches the longest bridge name first to avoid partial matches
    (e.g. "碧波廊桥" should match before "碧波").
    Uses a module-level cache (TTL 5 min) to avoid full table scan per request.
    """
    candidates = _get_bridge_candidates(db)
    for bridge_id, name in candidates:
        if name and name in question:
            return bridge_id
    return None
