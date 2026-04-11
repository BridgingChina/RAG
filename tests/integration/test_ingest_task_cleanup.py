"""Integration tests for _cleanup_task_data (issue #148 Bug #2).

Covers:
- FK ordering fix: source/chunks/links cleanup must not raise
  ForeignKeyViolation when the task's persisted ``source_id`` still
  references the source being deleted.
- Savepoint/error-contract: failures inside cleanup must raise a typed
  :class:`CleanupError` and leave the outer transaction usable.
- End-to-end retry endpoint: POST /retry on a failed task must return 200
  and flip status to 'syncing'.
- Batch-delete per-task isolation: one failing task must not nuke the
  rest of the batch.

These tests require a running PostgreSQL+pgvector instance.
They will be skipped if the DB is unavailable (see tests/conftest.py).
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from app.api.v1.ingest_tasks import CleanupError, _cleanup_task_data
from app.core.constants import EMBEDDING_DIM
from app.core.database import get_db
from app.main import app
from app.models import Chunk, ChunkBridgeLink, Source
from app.models.ingest_task import IngestTask


def _zero_vec() -> list[float]:
    return [0.0] * EMBEDDING_DIM


@pytest.fixture
def task_with_source(db_session, test_bridges):
    """Create a source + chunks + bridge links + ingest task mirroring real state."""
    db_session.execute(sql_text("DELETE FROM chunk_bridge_links"))
    db_session.execute(sql_text("DELETE FROM chunks"))
    db_session.execute(sql_text("DELETE FROM ingest_tasks"))
    db_session.execute(sql_text("DELETE FROM sources"))
    db_session.flush()

    source = Source(type="document", title="程阳永济桥.md")
    db_session.add(source)
    db_session.flush()

    target_bridge = test_bridges["target"]
    chunks = []
    for i in range(3):
        chunk = Chunk(
            source_id=source.id,
            content=f"桥段 {i}",
            embedding=_zero_vec(),
        )
        db_session.add(chunk)
        chunks.append(chunk)
    db_session.flush()

    for chunk in chunks:
        link = ChunkBridgeLink(
            chunk_id=chunk.id,
            bridge_id=target_bridge.id,
            role="primary",
            confidence=0.9,
            method="test",
        )
        db_session.add(link)
    db_session.flush()

    task = IngestTask(
        status="failed",
        file_name="程阳永济桥.md",
        file_type="md",
        source_id=source.id,
        error_message="429 too many requests",
    )
    db_session.add(task)
    db_session.flush()

    return {
        "task": task,
        "source": source,
        "chunks": chunks,
    }


# --- FK ordering regression (Bug #2 core) ---


def test_cleanup_task_data_removes_source_chunks_and_links(db_session, task_with_source):
    """Regression for #148 Bug #2: pre-fix, the Source DELETE raised
    ForeignKeyViolation because the persisted ``ingest_tasks`` row still
    referenced the source being deleted (``task.source_id = None`` was
    the LAST statement in the function, never reached the DB before the
    Source DELETE). Post-fix: cleanup must flush the task's source_id
    UPDATE first, then the Source DELETE succeeds.

    Uses ``db.flush()`` (not ``commit()``) so the conftest's transaction
    rollback fixture keeps working -- the FK check is non-deferrable and
    fires on flush, so commit is not required to reproduce.
    """
    task = task_with_source["task"]
    source_id = task_with_source["source"].id
    chunk_ids = [c.id for c in task_with_source["chunks"]]

    _cleanup_task_data(db_session, task)
    db_session.flush()  # triggers the FK check -- no commit needed

    # Post-conditions: everything tied to the task's source is gone
    assert task.source_id is None
    assert db_session.query(Source).filter(Source.id == source_id).count() == 0
    assert db_session.query(Chunk).filter(Chunk.id.in_(chunk_ids)).count() == 0
    assert (
        db_session.query(ChunkBridgeLink)
        .filter(ChunkBridgeLink.chunk_id.in_(chunk_ids))
        .count()
        == 0
    )
    # Task row itself survives -- only source linkage was cleaned
    assert (
        db_session.query(IngestTask).filter(IngestTask.id == task.id).count() == 1
    )


def test_cleanup_task_data_no_source_is_noop(db_session):
    """Task without source_id should be handled gracefully (no-op, idempotent)."""
    db_session.execute(sql_text("DELETE FROM ingest_tasks"))
    db_session.flush()

    task = IngestTask(
        status="failed",
        file_name="orphan.md",
        file_type="md",
        source_id=None,
    )
    db_session.add(task)
    db_session.flush()

    _cleanup_task_data(db_session, task)
    db_session.flush()

    assert task.source_id is None
    assert (
        db_session.query(IngestTask).filter(IngestTask.id == task.id).count() == 1
    )


# --- Savepoint / error-contract (C2 + C8) ---


def test_cleanup_task_data_raises_cleanup_error_on_db_failure(
    db_session, task_with_source
):
    """Savepoint contract: a DB error inside cleanup must roll back the
    savepoint, raise :class:`CleanupError`, and leave the outer session
    usable with the task's in-memory ``source_id`` restored.

    We inject the error by patching ``db.query(Source).delete()`` to raise
    :class:`SQLAlchemyError`. This is more robust than relying on a real
    FK violation because the test does not depend on the local DB schema
    having every FK constraint the model declares (some dev DBs drift
    from the model because ``Base.metadata.create_all`` does not ALTER
    existing tables).
    """
    from sqlalchemy.exc import InternalError

    task = task_with_source["task"]
    original_source_id = task.source_id

    real_query = db_session.query
    source_delete_raised = {"fired": False}

    def patched_query(*args, **kwargs):
        q = real_query(*args, **kwargs)
        # Identity check (``is``) avoids triggering SQLAlchemy ``__eq__`` on
        # column expressions like ``Chunk.id`` that appear in other calls.
        if any(a is Source for a in args):
            original_filter = q.filter

            def raising_filter(*f_args, **f_kwargs):
                filtered = original_filter(*f_args, **f_kwargs)

                def raising_delete(*_d_args, **_d_kwargs):
                    source_delete_raised["fired"] = True
                    raise InternalError(
                        "forced test failure on Source delete", None, Exception("boom")
                    )

                filtered.delete = raising_delete
                return filtered

            q.filter = raising_filter
        return q

    with patch.object(db_session, "query", side_effect=patched_query):
        with pytest.raises(CleanupError) as excinfo:
            _cleanup_task_data(db_session, task)

    assert source_delete_raised["fired"], "Source DELETE interceptor never fired"
    # In-memory source_id restored for caller consistency
    assert task.source_id == original_source_id
    assert excinfo.value.task_id == task.id
    assert excinfo.value.source_id == original_source_id
    assert isinstance(excinfo.value.cause, InternalError)
    # Outer session is still usable (savepoint isolated the error)
    assert db_session.query(IngestTask).count() >= 1


# --- Retry endpoint end-to-end (C5) ---


@pytest.fixture
def client(db_session):
    from app.api.v1.dependencies import get_current_user
    from app.models import User

    # Persist a real user row so AuditService.log() can write a row referencing
    # it (audit_logs.user_id has a FK to users.id).
    db_session.execute(sql_text("DELETE FROM audit_logs WHERE user_id IS NOT NULL"))
    db_session.execute(
        sql_text("DELETE FROM users WHERE username = 'cleanup_test_user'")
    )
    db_session.flush()
    test_user = User(
        username="cleanup_test_user",
        hashed_password="x",
        display_name="Cleanup Tester",
        is_active=True,
    )
    db_session.add(test_user)
    db_session.flush()

    def override_get_db():
        yield db_session

    def override_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_retry_endpoint_returns_200_and_resets_task(
    client, db_session, task_with_source
):
    """POST /api/v1/ingest-tasks/{id}/retry must return 200 and flip status
    to 'queued' (regression for #148 Bug #2 symptom: pre-fix this returned
    500 ForeignKeyViolation).

    After #152 the retry endpoint is pure enqueue -- the actual dispatch
    to _run_sync_and_parse happens in the ingest scheduler when capacity
    allows, so the task reaches 'queued' and NOT 'syncing' immediately.
    """
    task = task_with_source["task"]

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["error_message"] is None
    assert body["source_id"] is None


# --- Batch-delete per-task isolation (C10) ---


def test_batch_delete_isolates_per_task_failures(
    client, db_session, test_bridges
):
    """A cleanup failure on one task must NOT prevent sibling tasks in the
    same batch from being deleted. Failing tasks are reported via the
    ``failed`` field with a reason.
    """
    db_session.execute(sql_text("DELETE FROM chunk_bridge_links"))
    db_session.execute(sql_text("DELETE FROM chunks"))
    db_session.execute(sql_text("DELETE FROM ingest_tasks"))
    db_session.execute(sql_text("DELETE FROM sources"))
    db_session.flush()

    # Two sibling tasks, both eligible for delete
    source_a = Source(type="document", title="A.md")
    source_b = Source(type="document", title="B.md")
    db_session.add_all([source_a, source_b])
    db_session.flush()

    task_a = IngestTask(
        status="failed", file_name="A.md", file_type="md", source_id=source_a.id
    )
    task_b = IngestTask(
        status="failed", file_name="B.md", file_type="md", source_id=source_b.id
    )
    db_session.add_all([task_a, task_b])
    db_session.flush()

    # Force _cleanup_task_data to fail ONLY on task_a by raising
    # CleanupError via a patched implementation.
    real_cleanup = _cleanup_task_data

    def flaky_cleanup(db, task):
        if task.id == task_a.id:
            raise CleanupError(task.id, task.source_id, RuntimeError("forced A failure"))
        return real_cleanup(db, task)

    with patch("app.api.v1.ingest_tasks._cleanup_task_data", side_effect=flaky_cleanup):
        response = client.post(
            "/api/v1/ingest-tasks/batch-delete",
            json={"task_ids": [str(task_a.id), str(task_b.id)]},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert str(task_b.id) in body["deleted"]
    assert len(body["failed"]) == 1
    assert body["failed"][0]["task_id"] == str(task_a.id)
    assert "forced A failure" in body["failed"][0]["reason"]
