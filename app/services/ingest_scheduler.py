"""Ingest task scheduler — global concurrency limiter for LLM pipeline.

Problem this solves (issue #152):
    The provider layer has no global concurrency limit, so user click count
    maps 1:1 to upstream API concurrency. When a user retries many failed
    tasks in quick succession, the resulting burst saturates the Zhipu rate
    limiter and every concurrent retry window lines up inside the same
    cooldown, failing together no matter how big the per-task retry budget
    is. See #148 / #149 / #150 / #151 for the retry-budget story.

Design (see plans/streamed-bubbling-newt.md and issue #152):
    - ``/retry``, ``/confirm``, and ``create_ingest_task`` endpoints no
      longer trigger BackgroundTask directly. They set the task status to
      ``queued`` or ``queued_for_indexing`` and return immediately.
    - This module runs a single FIFO scheduler loop inside the FastAPI
      lifespan. Every ``settings.ingest_scheduler_interval_seconds`` it
      checks how many tasks are in RUNNING_STATUSES and dispatches up to
      ``settings.ingest_max_concurrent - running`` queued tasks.
    - A Postgres *transaction-scoped* advisory lock (``pg_try_advisory_xact_lock``)
      elects a single scheduler across multiple uvicorn workers. Production
      currently runs 1 worker, but the lock makes the design forward-compatible
      with multi-worker deployments without code changes.
    - Dispatch uses ``asyncio.create_task`` (not FastAPI BackgroundTasks)
      because the scheduler is not in an HTTP request context. Dispatched
      tasks run in the same event loop as the scheduler.

Invariants:
    - ``queued`` / ``queued_for_indexing`` are *pending* states. They do
      NOT count against RUNNING_STATUSES and delete endpoints still allow
      cancelling them.
    - Only ``syncing`` / ``parsing`` / ``indexing`` count as running.
    - FIFO order via ``ORDER BY updated_at ASC`` — the moment they entered
      the queue.
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import logger
from app.models.ingest_task import IngestTask

# Distinct from ``database.py``'s init-lock (606059278) and
# ``migrate_db.py``'s migration-lock (606059278). A different key means
# the scheduler's lease does not block init or migration.
INGEST_SCHEDULER_LOCK_ID = 494956380

# Mirrors ``ingest_tasks.py::RUNNING_STATUSES`` but duplicated here to
# avoid importing from the API layer (circular import risk via
# ``_run_sync_and_parse``). Keep in sync manually; the unit test
# ``test_running_statuses_match`` guards against drift.
RUNNING_STATUSES: frozenset[str] = frozenset(("syncing", "parsing", "indexing"))

# States the scheduler will pick up and dispatch.
QUEUED_STATUSES: frozenset[str] = frozenset(("queued", "queued_for_indexing"))


async def ingest_scheduler_loop() -> None:
    """Scheduler main loop — lifespan-level background task.

    Wraps :func:`_scheduler_tick` in an infinite loop with exception
    swallowing so a single bad tick does not kill the loop. If the loop
    itself dies, the container restart recovers.
    """
    logger.info(
        "Ingest scheduler started (max_concurrent=%d, interval=%.1fs)",
        settings.ingest_max_concurrent,
        settings.ingest_scheduler_interval_seconds,
    )
    while True:
        try:
            await _scheduler_tick()
        except Exception:  # noqa: BLE001 — intentional catch-all
            logger.exception("Ingest scheduler tick failed")
        await asyncio.sleep(settings.ingest_scheduler_interval_seconds)


async def _scheduler_tick() -> list[tuple[str, uuid.UUID]]:
    """Run a single scheduler iteration.

    Returns the list of dispatched ``(kind, task_id)`` pairs for tests and
    observability. On normal operation this is empty when either (a) the
    current worker is not the leader or (b) there is no capacity.
    """
    db: Session = SessionLocal()
    dispatch: list[tuple[str, uuid.UUID]] = []
    try:
        # Transaction-scoped advisory lock — releases on commit/rollback.
        # pg_try_advisory_xact_lock returns BOOLEAN without blocking.
        got_lock = db.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": INGEST_SCHEDULER_LOCK_ID},
        ).scalar()
        if not got_lock:
            db.rollback()
            return dispatch

        running = db.scalar(
            select(func.count())
            .select_from(IngestTask)
            .where(IngestTask.status.in_(RUNNING_STATUSES))
        )
        capacity = settings.ingest_max_concurrent - (running or 0)
        if capacity <= 0:
            db.commit()  # release the lock cleanly
            return dispatch

        # FIFO by updated_at. SKIP LOCKED is belt-and-suspenders against
        # a concurrent manual UPDATE on the same row — neither should
        # happen once the advisory lock is held, but the cost is zero.
        queued_tasks = (
            db.execute(
                select(IngestTask)
                .where(IngestTask.status.in_(QUEUED_STATUSES))
                .order_by(IngestTask.updated_at.asc())
                .limit(capacity)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for task in queued_tasks:
            if task.status == "queued":
                task.status = "syncing"
                dispatch.append(("sync", task.id))
            elif task.status == "queued_for_indexing":
                task.status = "indexing"
                dispatch.append(("index", task.id))
            # else: a race snuck an unexpected status in — skip it

        db.commit()  # persists status flips AND releases the advisory lock
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # Dispatch outside the scheduler's own DB session. Each dispatched
    # task opens its own SessionLocal via _run_sync_and_parse / _run_indexing.
    if dispatch:
        logger.info(
            "Ingest scheduler dispatching %d task(s): %s",
            len(dispatch),
            [f"{kind}:{tid}" for kind, tid in dispatch],
        )
        # Import lazily to avoid a circular import with app/api/v1/ingest_tasks.py
        from app.api.v1.ingest_tasks import _run_indexing, _run_sync_and_parse

        for kind, task_id in dispatch:
            if kind == "sync":
                asyncio.create_task(_run_sync_and_parse(task_id))
            else:
                asyncio.create_task(_run_indexing(task_id))

    return dispatch
