"""Unit tests for ``app.services.ingest_scheduler`` (issue #152).

These tests don't touch a real database. They mock ``SessionLocal``,
``asyncio.create_task``, and the lazy-imported runners
(``_run_sync_and_parse`` / ``_run_indexing``) so we can exercise the
scheduler's branching logic without spinning up Postgres or an HTTP
client.

Integration-style tests that exercise the full path with a real
Postgres live in ``tests/integration/test_ingest_scheduler_e2e.py``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ingest_scheduler import (
    INGEST_SCHEDULER_LOCK_ID,
    QUEUED_STATUSES,
    RUNNING_STATUSES,
    _scheduler_tick,
)


@pytest.fixture
def mock_session_factory():
    """Build a factory that returns a fully mocked SQLAlchemy Session.

    Using a factory (not a fixture returning a single session) lets
    individual tests configure the mock before patching ``SessionLocal``.
    """
    def _build(
        *,
        lock_acquired: bool = True,
        running_count: int = 0,
        queued_tasks: list | None = None,
    ) -> MagicMock:
        session = MagicMock(name="Session")
        session.commit = MagicMock()
        session.rollback = MagicMock()
        session.close = MagicMock()

        # First execute() is pg_try_advisory_xact_lock — returns a result
        # whose .scalar() yields the boolean.
        lock_result = MagicMock()
        lock_result.scalar = MagicMock(return_value=lock_acquired)

        # Third execute() is the queued SELECT — returns a result whose
        # .scalars().all() yields the rows.
        queued_result = MagicMock()
        queued_result.scalars.return_value.all.return_value = queued_tasks or []

        session.execute = MagicMock(side_effect=[lock_result, queued_result])
        # db.scalar() (for the running-count query, the 2nd DB interaction)
        session.scalar = MagicMock(return_value=running_count)
        return session

    return _build


def _make_task(status: str, *, updated_offset_seconds: int = 0) -> MagicMock:
    """Build a mock IngestTask with an id and mutable ``status``."""
    task = MagicMock(name=f"IngestTask({status})")
    task.id = uuid.uuid4()
    task.status = status
    task.updated_at = datetime.now(timezone.utc) + timedelta(
        seconds=updated_offset_seconds
    )
    return task


# --- Invariants ---------------------------------------------------------


def test_running_statuses_match_api_constant():
    """Scheduler RUNNING_STATUSES must stay in sync with the API layer's."""
    from app.api.v1.ingest_tasks import RUNNING_STATUSES as API_RUNNING

    assert RUNNING_STATUSES == frozenset(API_RUNNING)


def test_queued_statuses_not_in_running():
    """Queued states must NOT count as running — otherwise delete would
    block on pending tasks, which is wrong by design (see plan)."""
    assert QUEUED_STATUSES.isdisjoint(RUNNING_STATUSES)


def test_lock_id_distinct_from_database_init_lock():
    """Must not collide with database.py's init lock (606059278) or
    migrate_db.py's migration lock."""
    assert INGEST_SCHEDULER_LOCK_ID != 606059278


# --- Lock contention ---------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_skips_when_not_leader(mock_session_factory):
    """pg_try_advisory_xact_lock returning False should short-circuit."""
    session = mock_session_factory(lock_acquired=False)
    with patch(
        "app.services.ingest_scheduler.SessionLocal", return_value=session
    ):
        dispatched = await _scheduler_tick()

    assert dispatched == []
    session.rollback.assert_called_once()
    # Must NOT have done the running-count query after failing the lock
    session.scalar.assert_not_called()


# --- Capacity enforcement ----------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_skips_when_capacity_exhausted(
    mock_session_factory, monkeypatch
):
    """If running count equals max_concurrent, no dispatch."""
    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 2
    )
    session = mock_session_factory(lock_acquired=True, running_count=2)

    with patch(
        "app.services.ingest_scheduler.SessionLocal", return_value=session
    ):
        dispatched = await _scheduler_tick()

    assert dispatched == []
    session.commit.assert_called_once()  # commit to release the advisory lock
    # We should not have queried the queued list at all
    assert session.execute.call_count == 1  # only the lock call


# --- Dispatch happy path ------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_dispatches_queued_task_for_sync(
    mock_session_factory, monkeypatch
):
    """A single queued task should flip to 'syncing' and dispatch sync runner."""
    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 2
    )
    task = _make_task("queued")
    session = mock_session_factory(
        lock_acquired=True, running_count=0, queued_tasks=[task]
    )

    with (
        patch(
            "app.services.ingest_scheduler.SessionLocal", return_value=session
        ),
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ) as sync_runner,
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ) as index_runner,
    ):
        dispatched = await _scheduler_tick()

    assert dispatched == [("sync", task.id)]
    assert task.status == "syncing"
    session.commit.assert_called_once()
    # create_task schedules the coroutine — let the loop run it
    import asyncio
    await asyncio.sleep(0)
    sync_runner.assert_called_once_with(task.id)
    index_runner.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_tick_dispatches_queued_for_indexing(
    mock_session_factory, monkeypatch
):
    """queued_for_indexing should flip to 'indexing' and dispatch index runner."""
    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 2
    )
    task = _make_task("queued_for_indexing")
    session = mock_session_factory(
        lock_acquired=True, running_count=0, queued_tasks=[task]
    )

    with (
        patch(
            "app.services.ingest_scheduler.SessionLocal", return_value=session
        ),
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ) as sync_runner,
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ) as index_runner,
    ):
        dispatched = await _scheduler_tick()

    assert dispatched == [("index", task.id)]
    assert task.status == "indexing"
    import asyncio
    await asyncio.sleep(0)
    index_runner.assert_called_once_with(task.id)
    sync_runner.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_tick_dispatches_mixed_queue(
    mock_session_factory, monkeypatch
):
    """Mixed queued + queued_for_indexing — each routed to the right runner."""
    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 5
    )
    sync_task = _make_task("queued", updated_offset_seconds=-30)
    index_task = _make_task("queued_for_indexing", updated_offset_seconds=-20)
    session = mock_session_factory(
        lock_acquired=True,
        running_count=0,
        queued_tasks=[sync_task, index_task],
    )

    with (
        patch(
            "app.services.ingest_scheduler.SessionLocal", return_value=session
        ),
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ),
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ),
    ):
        dispatched = await _scheduler_tick()

    assert ("sync", sync_task.id) in dispatched
    assert ("index", index_task.id) in dispatched
    assert sync_task.status == "syncing"
    assert index_task.status == "indexing"


@pytest.mark.asyncio
async def test_scheduler_tick_respects_capacity_with_queued_tasks(
    mock_session_factory, monkeypatch
):
    """With 1 slot free and 3 queued, only 1 should be dispatched."""
    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 2
    )
    # running_count=1, capacity=1 → limit=1 → only first row returned
    returned = [_make_task("queued", updated_offset_seconds=-60)]
    session = mock_session_factory(
        lock_acquired=True, running_count=1, queued_tasks=returned
    )

    with (
        patch(
            "app.services.ingest_scheduler.SessionLocal", return_value=session
        ),
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ),
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ),
    ):
        dispatched = await _scheduler_tick()

    assert len(dispatched) == 1
    # Verify the SELECT used LIMIT(capacity) — we can't introspect the
    # query directly, but the scheduler trusts the mock to return the
    # right count. This test protects against the scheduler *ignoring*
    # capacity and dispatching more than returned.


# --- Exception safety --------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_rolls_back_on_exception(mock_session_factory):
    """An unexpected error after lock acquisition must rollback and propagate."""
    session = mock_session_factory(lock_acquired=True, running_count=0)
    # Make scalar raise (simulates DB failure during running-count query)
    session.scalar = MagicMock(side_effect=RuntimeError("boom"))

    with patch(
        "app.services.ingest_scheduler.SessionLocal", return_value=session
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await _scheduler_tick()

    session.rollback.assert_called_once()
    session.close.assert_called_once()
    # commit must NOT have been called — we want the lock released by rollback
    session.commit.assert_not_called()
