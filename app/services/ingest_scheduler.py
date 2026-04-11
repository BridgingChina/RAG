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
from app.models.ingest_task import (
    QUEUED_STATUSES,
    RUNNING_STATUSES,
    IngestTask,
)

# Lock ID 494956380 is distinct from the shared init/migration lock
# (606059278, used by both ``app/core/database.py::init_database`` and
# ``scripts/migrate_db.py``) so scheduler ticks never block startup or
# migration, and vice versa.
INGEST_SCHEDULER_LOCK_ID = 494956380

# Tracks in-flight dispatched tasks so asyncio doesn't garbage-collect
# them while they're still running (asyncio only keeps weak references
# to tasks created via ``create_task``). See ``_schedule_runner`` below.
_dispatched_tasks: set[asyncio.Task] = set()


async def ingest_scheduler_loop() -> None:
    """Scheduler main loop — lifespan-level background task.

    Wraps :func:`_scheduler_tick` in an infinite loop with exception
    swallowing so a single bad tick does not kill the loop. ``asyncio.CancelledError``
    (from lifespan shutdown) propagates normally because it inherits from
    ``BaseException``, not ``Exception``. The double-nested try/except on
    ``logger.exception`` is intentional: if the logger backend itself
    raises (formatter crash, handler network timeout, etc.) we fall
    through to stderr instead of letting the loop die.

    If this loop coroutine ever dies (as opposed to a single bad tick),
    ``main.py::_on_scheduler_done`` will log CRITICAL so ops can spot it.
    """
    import os
    import sys
    import traceback

    logger.info(
        "Ingest scheduler started (pid=%d, max_concurrent=%d, interval=%.1fs)",
        os.getpid(),
        settings.ingest_max_concurrent,
        settings.ingest_scheduler_interval_seconds,
    )
    while True:
        try:
            await _scheduler_tick()
        except Exception:  # noqa: BLE001 — intentional catch-all
            try:
                logger.exception("Ingest scheduler tick failed")
            except Exception:
                # Logger itself broke. Last-resort stderr so the loop
                # keeps running instead of dying with a broken logger.
                print(
                    "INGEST SCHEDULER: tick failed AND logger broke",
                    file=sys.stderr,
                )
                traceback.print_exc(file=sys.stderr)
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
            else:
                # QUEUED_STATUSES filter should make this unreachable.
                # If it fires, a new queued status was added to the
                # query filter but not to this dispatch switch.
                logger.warning(
                    "Ingest scheduler picked task %s with unexpected "
                    "status %r -- skipping. QUEUED_STATUSES and the "
                    "dispatch switch are out of sync.",
                    task.id,
                    task.status,
                )

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
            ", ".join(f"{kind}:{tid}" for kind, tid in dispatch),
        )
        for kind, task_id in dispatch:
            _schedule_runner(kind, task_id)

    return dispatch


def _schedule_runner(kind: str, task_id: uuid.UUID) -> asyncio.Task:
    """Dispatch a runner coroutine with full lifecycle tracking.

    Three things this does that a naked ``asyncio.create_task`` does not:

    1. Adds the handle to ``_dispatched_tasks`` so the event loop keeps
       a strong reference — prevents asyncio from garbage-collecting an
       in-flight task under GC pressure.
    2. Attaches a done-callback that, if the runner raised an unhandled
       exception, logs it AND marks the task ``failed`` out-of-band via
       a fresh session. Without this, constructor errors in the runner
       (e.g. ``R2StorageService()`` raising ``NoRegionError``) would
       leak through the runner's own ``try/except`` and the task would
       sit in ``syncing``/``indexing`` until ``cleanup_stale_running_tasks``
       reaper runs 60 minutes later.
    3. Lazy-imports ``_run_sync_and_parse`` / ``_run_indexing`` inside
       this function to avoid a circular import with
       ``app/api/v1/ingest_tasks.py``.
    """
    from app.api.v1.ingest_tasks import _run_indexing, _run_sync_and_parse

    if kind == "sync":
        coro = _run_sync_and_parse(task_id)
    elif kind == "index":
        coro = _run_indexing(task_id)
    else:
        raise ValueError(f"Unknown runner kind: {kind!r}")

    task = asyncio.create_task(coro, name=f"ingest-{kind}-{task_id}")
    _dispatched_tasks.add(task)
    task.add_done_callback(_dispatched_tasks.discard)
    task.add_done_callback(lambda t: _on_runner_done(t, kind, task_id))
    return task


def _on_runner_done(
    task: asyncio.Task,
    kind: str,
    task_id: uuid.UUID,
) -> None:
    """Done-callback for dispatched runners.

    Runners own their own try/except to call ``IngestTaskService._fail``
    for expected errors. This callback catches everything else: bare
    cancellation, constructor-phase exceptions that bypass the runner's
    try block, lazy-import failures. On any such case it marks the task
    ``failed`` via a fresh session so the capacity slot is released.
    """
    if task.cancelled():
        logger.error(
            "Ingest runner cancelled mid-flight: kind=%s task_id=%s",
            kind,
            task_id,
        )
        _mark_failed_out_of_band(task_id, f"Runner cancelled ({kind})")
        return

    exc = task.exception()
    if exc is None:
        return  # normal completion — runner wrote its own final status

    logger.error(
        "Ingest runner crashed with unhandled exception: kind=%s task_id=%s",
        kind,
        task_id,
        exc_info=exc,
    )
    _mark_failed_out_of_band(
        task_id,
        f"Runner crashed before its own error handler could catch "
        f"({kind}): {type(exc).__name__}: {exc}",
    )


def _mark_failed_out_of_band(task_id: uuid.UUID, error_message: str) -> None:
    """Mark a task ``failed`` using a fresh session, no-op on any error.

    Used from the runner done-callback after the normal ``_fail`` path
    has been bypassed. The 60-minute stale reaper is the backstop if
    this too fails for any reason.
    """
    try:
        db = SessionLocal()
        try:
            db.execute(
                text(
                    "UPDATE ingest_tasks "
                    "SET status = 'failed', "
                    "    error_message = :msg, "
                    "    updated_at = now() "
                    "WHERE id = :id"
                ),
                {"msg": error_message[:1000], "id": task_id},
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.exception(
            "Out-of-band fail-marking ALSO failed for task %s; "
            "stale reaper is the backstop",
            task_id,
        )
