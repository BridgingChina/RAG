"""Background cron jobs for reindexing stale chunks and cleaning up stale tasks."""
import asyncio
from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.core.logging import logger
from app.services.chunk_editor import reindex_source_chunks
from app.services.tokenizer import Tokenizer, default_user_dict_path


def _next_run_time(hour: int = 3) -> datetime:
    """Calculate next occurrence of the given hour (local time)."""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


async def uploading_cleanup_loop(interval_minutes: int = 30):
    """Periodically clean up stale uploading ingest tasks."""
    from app.services.ingest_task_service import cleanup_stale_uploading_tasks

    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            db = SessionLocal()
            try:
                cleaned = cleanup_stale_uploading_tasks(db)
                if cleaned:
                    logger.info("Uploading cleanup: marked %d stale tasks as failed", cleaned)
            finally:
                db.close()
        except Exception:
            logger.exception("Uploading cleanup: failed")


async def reindex_cron_loop(hour: int = 3):
    """Run reindex for all stale chunks daily at the given hour."""
    while True:
        next_run = _next_run_time(hour)
        wait_seconds = (next_run - datetime.now()).total_seconds()
        logger.info(f"Reindex cron: next run at {next_run} ({wait_seconds:.0f}s from now)")
        await asyncio.sleep(wait_seconds)

        logger.info("Reindex cron: starting stale chunk reindex...")
        try:
            _run_reindex()
        except Exception:
            logger.exception("Reindex cron: failed")
        logger.info("Reindex cron: done")


def _run_reindex():
    """Synchronous reindex of all stale chunks across all sources."""
    from sqlalchemy import distinct

    from app.models import Chunk

    db = SessionLocal()
    tokenizer = Tokenizer(user_dict_path=default_user_dict_path())

    try:
        # Find all sources with stale chunks
        source_ids = (
            db.query(distinct(Chunk.source_id))
            .filter(Chunk.needs_reindex == True)  # noqa: E712
            .all()
        )

        total = 0
        for (source_id,) in source_ids:
            result = reindex_source_chunks(
                db=db,
                source_id=source_id,
                tokenizer=tokenizer,
                provider=None,  # Skip embedding for cron (too expensive)
                force=False,
            )
            total += result["chunks_reindexed"]

        db.commit()
        logger.info(f"Reindex cron: reindexed {total} chunks across {len(source_ids)} sources")
    finally:
        db.close()
