"""Reconcile orphan user rows — Phase 2 Task 2.E.2 + 2.E.4.

Scans distinct ``user_id`` values in the three user-scoped tables and
HEAD-probes each against the auth Worker's
``/api/auth/users/{id}/exists`` endpoint. Any user_id that the auth
Worker doesn't know about is orphaned (user was deleted inside D1 but the
webhook purge never reached FastAPI) and gets a local purge.

The HEAD endpoint itself lives in the auth Worker (Phase 2 Task 2.E.3,
tracked separately). Until it ships, this cron is wired but inert — it
will log "auth worker unreachable" and return 0.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from sqlalchemy import text as sql_text

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# Check interval: 24h (set by lifespan caller; this module is pure logic).
RECONCILE_INTERVAL_SECONDS = 24 * 60 * 60


async def _user_exists(client: httpx.AsyncClient, user_id: str) -> bool | None:
    """Return True/False when the auth Worker answers, None on transport error.

    Treating unreachable as "unknown" rather than "gone" is critical: a
    transient auth Worker outage must NOT cascade into purging every live
    user's RAG state.
    """
    url = f"{settings.auth_worker_base_url.rstrip('/')}/api/auth/users/{user_id}/exists"
    try:
        resp = await client.head(url, timeout=10.0)
    except httpx.HTTPError as exc:
        logger.warning("auth worker unreachable for %s: %s", user_id, exc)
        return None
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        return False
    logger.warning(
        "unexpected status %d from auth worker for %s", resp.status_code, user_id
    )
    return None


def _collect_user_ids(db) -> set[str]:
    """Collect the union of user_ids across the three user-scoped tables."""
    user_ids: set[str] = set()
    for table in ("favorites", "review_progress", "view_history"):
        rows = db.execute(sql_text(f"SELECT DISTINCT user_id FROM {table}")).scalars().all()
        user_ids.update(rows)
    return user_ids


def _purge_user(db, user_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("favorites", "review_progress", "view_history"):
        result = db.execute(
            sql_text(f"DELETE FROM {table} WHERE user_id = :uid"),
            {"uid": user_id},
        )
        counts[table] = result.rowcount or 0
    db.execute(
        sql_text("UPDATE audit_logs SET user_id = NULL WHERE user_id = :uid"),
        {"uid": user_id},
    )
    db.commit()
    return counts


async def reconcile_once() -> int:
    """Run one reconcile pass. Returns number of users purged."""
    if not settings.auth_worker_base_url:
        logger.info("reconcile skipped: AUTH_WORKER_BASE_URL unset")
        return 0

    db = SessionLocal()
    try:
        user_ids = _collect_user_ids(db)
        if not user_ids:
            return 0

        async with httpx.AsyncClient() as client:
            checks = await asyncio.gather(
                *(_user_exists(client, uid) for uid in user_ids)
            )

        purged = 0
        for user_id, exists in zip(user_ids, checks):
            if exists is False:
                counts = _purge_user(db, user_id)
                logger.info("purged orphan user %s: %s", user_id, counts)
                purged += 1
            # exists is None → transport error, skip silently (will retry
            # next cron tick instead of deleting under uncertainty).
        return purged
    finally:
        db.close()


async def reconcile_orphans_loop() -> None:
    """Long-running loop called from lifespan — wakes every 24h."""
    while True:
        try:
            purged = await reconcile_once()
            if purged:
                logger.info("reconcile pass complete: %d orphan(s) purged", purged)
        except Exception:
            logger.exception("reconcile pass failed")
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
