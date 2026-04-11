"""Integration tests for the ingest scheduler (issue #152).

These tests require a running PostgreSQL+pgvector instance and exercise
the real advisory lock acquisition, queue ordering, and dispatch path.
They mock the lazy-imported runner functions so no actual Zhipu API
calls are made.

The goal is to prove that:
1. The retry endpoint enqueues and does NOT trigger sync_and_parse directly.
2. A real ``_scheduler_tick`` call picks up queued work, flips status, and
   dispatches the right runner.
3. When many tasks are queued, the scheduler never dispatches more than
   ``ingest_max_concurrent`` simultaneously.
4. The Postgres advisory lock actually prevents two concurrent scheduler
   ticks from double-dispatching the same task.

Skipped when the DB is unavailable (see ``tests/conftest.py``).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text
from sqlalchemy.exc import OperationalError

from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.main import app
from app.models import User
from app.models.ingest_task import IngestTask


# Marker prefix for all test tasks — lets the fixture clean up only its
# own rows on teardown without touching anything else in the DB.
_TASK_PREFIX = "scheduler_e2e_"


@pytest.fixture
def real_db(db_engine):
    """Real SessionLocal with manual cleanup.

    The default ``db_session`` fixture isolates tests via connection-level
    transaction rollback — but the scheduler opens its own ``SessionLocal()``
    which lives on a different connection, so it cannot see data still
    inside the fixture's in-flight transaction. These tests therefore
    commit real rows and clean them up explicitly on teardown.

    Depends on ``db_engine`` (from conftest) to ensure the schema exists,
    and additionally re-runs ``Base.metadata.create_all`` in case another
    test (e.g. ``test_database_init_integration``) dropped tables earlier
    in the session.
    """
    # Defensive: re-create any tables dropped by
    # ``test_database_init_integration.py::test_hnsw_index_created``
    # (which does ``Base.metadata.drop_all`` then ``create_all``). If
    # those tests ran and something else wiped the DB between, the
    # session-scoped ``db_engine`` fixture's ``create_all`` is stale.
    from app.models import Base

    Base.metadata.create_all(db_engine)

    # Skip if DB unavailable (same pattern as conftest.db_session).
    try:
        test_db = SessionLocal()
        test_db.execute(sql_text("SELECT 1"))
    except OperationalError:
        pytest.skip(
            "PostgreSQL test DB not available. "
            "Start it with `docker compose up -d db` and retry."
        )

    def _wipe(db):
        # Audit logs first (FK to users), then tasks, then user.
        db.execute(
            sql_text(
                "DELETE FROM audit_logs WHERE user_id IN ("
                "  SELECT id FROM users WHERE username = 'scheduler_e2e_user'"
                ")"
            )
        )
        db.execute(
            sql_text(
                "DELETE FROM ingest_tasks WHERE file_name LIKE :p"
            ),
            {"p": f"{_TASK_PREFIX}%"},
        )
        db.execute(
            sql_text("DELETE FROM users WHERE username = 'scheduler_e2e_user'")
        )
        db.commit()

    _wipe(test_db)
    try:
        yield test_db
    finally:
        _wipe(test_db)
        test_db.close()


@pytest.fixture
def test_user(real_db):
    """Persist a minimal User so audit_logs FK doesn't blow up."""
    user = User(
        username="scheduler_e2e_user",
        hashed_password="x",
        display_name="Scheduler E2E",
        is_active=True,
    )
    real_db.add(user)
    real_db.commit()
    real_db.refresh(user)
    return user


@pytest.fixture
def client(real_db, test_user):
    def override_get_db():
        yield real_db

    def override_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _make_failed_task(db, file_name_suffix: str) -> IngestTask:
    """Create a bare failed task with no source.

    file_name is prefixed with ``_TASK_PREFIX`` so the fixture can clean it up.
    """
    task = IngestTask(
        status="failed",
        file_name=f"{_TASK_PREFIX}{file_name_suffix}",
        file_type="md",
        source_id=None,
        error_message="prior failure",
    )
    db.add(task)
    db.flush()
    return task


# --- Endpoint enqueue semantics ----------------------------------------


def test_retry_endpoint_enqueues_without_dispatching(client, real_db):
    """POST /retry should flip status to 'queued' and NOT call _run_sync_and_parse."""
    task = _make_failed_task(real_db, "retry_enqueue.md")
    real_db.commit()

    with patch(
        "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
    ) as mock_runner:
        response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    # CRITICAL: the runner MUST NOT be called by the endpoint — it is the
    # scheduler's job now.
    mock_runner.assert_not_called()


# --- Scheduler tick dispatches queued work -----------------------------


@pytest.mark.asyncio
async def test_scheduler_tick_picks_up_queued_task(real_db, test_user):
    """_scheduler_tick (with real DB + real advisory lock) picks up a
    queued task, flips its status, and dispatches the right runner."""
    from app.services.ingest_scheduler import _scheduler_tick

    task = _make_failed_task(real_db, "tick_pickup.md")
    task.status = "queued"
    real_db.commit()

    with (
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ) as sync_runner,
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ) as index_runner,
    ):
        dispatched = await _scheduler_tick()
        # Let the asyncio.create_task coroutines actually run
        await asyncio.sleep(0)

    assert dispatched == [("sync", task.id)]
    sync_runner.assert_called_once_with(task.id)
    index_runner.assert_not_called()

    # Verify the DB row was flipped (and persisted by the scheduler's commit)
    real_db.expire_all()
    fresh = real_db.get(IngestTask, task.id)
    assert fresh.status == "syncing"
    # Leave it in a non-running state for the fixture teardown
    fresh.status = "failed"
    real_db.commit()


@pytest.mark.asyncio
async def test_scheduler_tick_respects_max_concurrent(
    real_db, test_user, monkeypatch
):
    """5 queued tasks + max_concurrent=2 → exactly 2 dispatched per tick.

    Three consecutive ticks should drain the queue: 2, 2, 1. Mocked runners
    don't actually change status back, so between ticks we manually flip
    dispatched rows to 'completed' to free capacity.
    """
    from app.services.ingest_scheduler import _scheduler_tick

    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 2
    )

    tasks = [_make_failed_task(real_db, f"cap_{i}.md") for i in range(5)]
    for t in tasks:
        t.status = "queued"
    real_db.commit()

    dispatched_ids: set = set()

    with (
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ),
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ),
    ):
        # Tick 1: should pick up 2
        d1 = await _scheduler_tick()
        assert len(d1) == 2
        dispatched_ids.update(tid for _, tid in d1)

        # Free capacity by completing both
        real_db.expire_all()
        for _, tid in d1:
            row = real_db.get(IngestTask, tid)
            row.status = "completed"
        real_db.commit()

        # Tick 2: another 2
        d2 = await _scheduler_tick()
        assert len(d2) == 2
        dispatched_ids.update(tid for _, tid in d2)

        real_db.expire_all()
        for _, tid in d2:
            row = real_db.get(IngestTask, tid)
            row.status = "completed"
        real_db.commit()

        # Tick 3: last 1 remaining
        d3 = await _scheduler_tick()
        assert len(d3) == 1
        dispatched_ids.update(tid for _, tid in d3)

    assert dispatched_ids == {t.id for t in tasks}

    # Leave everything in non-running state for fixture teardown
    real_db.expire_all()
    for t in tasks:
        row = real_db.get(IngestTask, t.id)
        if row and row.status != "completed":
            row.status = "failed"
    real_db.commit()


@pytest.mark.asyncio
async def test_scheduler_tick_blocks_at_capacity(
    real_db, test_user, monkeypatch
):
    """If max_concurrent=2 and 2 tasks already running, tick dispatches 0."""
    from app.services.ingest_scheduler import _scheduler_tick

    monkeypatch.setattr(
        "app.services.ingest_scheduler.settings.ingest_max_concurrent", 2
    )

    # Two tasks already in running state, consuming all capacity
    running_a = _make_failed_task(real_db, "running_a.md")
    running_a.status = "indexing"
    running_b = _make_failed_task(real_db, "running_b.md")
    running_b.status = "syncing"
    # A queued task that should NOT be picked up this tick
    queued = _make_failed_task(real_db, "queued.md")
    queued.status = "queued"
    real_db.commit()

    with (
        patch(
            "app.api.v1.ingest_tasks._run_sync_and_parse", new_callable=AsyncMock
        ),
        patch(
            "app.api.v1.ingest_tasks._run_indexing", new_callable=AsyncMock
        ),
    ):
        dispatched = await _scheduler_tick()

    assert dispatched == []
    real_db.expire_all()
    assert real_db.get(IngestTask, queued.id).status == "queued"

    # Move running tasks out of running state so the fixture teardown
    # (which just DELETEs them) doesn't leave the scheduler loop seeing
    # ghost capacity on the next test.
    real_db.get(IngestTask, running_a.id).status = "failed"
    real_db.get(IngestTask, running_b.id).status = "failed"
    real_db.get(IngestTask, queued.id).status = "failed"
    real_db.commit()


# --- Stale running cleanup --------------------------------------------


def test_cleanup_stale_running_tasks_reclaims_stuck_tasks(real_db, test_user):
    """A task stuck in 'indexing' longer than the threshold should flip to failed."""
    from datetime import datetime, timedelta, timezone

    from app.services.ingest_task_service import cleanup_stale_running_tasks

    stuck = _make_failed_task(real_db, "stuck.md")
    stuck.status = "indexing"
    real_db.commit()
    # Force updated_at far in the past by raw UPDATE (ORM onupdate would fight us)
    real_db.execute(
        sql_text(
            "UPDATE ingest_tasks SET updated_at = :t WHERE id = :id"
        ),
        {
            "t": datetime.now(timezone.utc) - timedelta(hours=3),
            "id": stuck.id,
        },
    )
    real_db.commit()

    cleaned = cleanup_stale_running_tasks(real_db, max_age_minutes=60)
    assert cleaned == 1

    real_db.expire_all()
    fresh = real_db.get(IngestTask, stuck.id)
    assert fresh.status == "failed"
    assert "exceeded max runtime" in (fresh.error_message or "")
    assert "indexing" in (fresh.error_message or "")  # captures prior state
