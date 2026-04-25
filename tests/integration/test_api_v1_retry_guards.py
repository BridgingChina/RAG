"""Integration tests for the retry endpoint's status guards + cooldown +
chunks_indexed progress signal (P0+P3 from 2026-04-24 incident RCA).

Reference: 2026-04-24 incident — user clicked retry 5x within 2.5h on the
same task against a Zhipu 429 storm. Each retry re-failed and the user
had no signal that anything was happening. This file pins:
- 4 retry rejection paths (running / queued / not_retriable / cooldown)
- structured detail dict shape for the frontend to consume
- chunks_indexed live progress when status == 'indexing'
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from app.api.v1.dependencies import get_current_user
from app.core.constants import EMBEDDING_DIM
from app.core.database import get_db
from app.main import app
from app.models import Chunk, Source
from app.models.current_user import CurrentUser
from app.models.ingest_task import IngestTask


def _zero_vec() -> list[float]:
    return [0.0] * EMBEDDING_DIM


@pytest.fixture
def client(db_session):
    test_user = CurrentUser(
        id="retry_guard_test_user",
        email="retry@test",
        role="admin",
    )

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


def _clean_ingest(db_session):
    db_session.execute(sql_text("DELETE FROM chunk_bridge_links"))
    db_session.execute(sql_text("DELETE FROM chunks"))
    db_session.execute(sql_text("DELETE FROM ingest_tasks"))
    db_session.execute(sql_text("DELETE FROM sources"))
    db_session.flush()


def _make_task(db_session, status: str, *, source: Source | None = None) -> IngestTask:
    task = IngestTask(
        status=status,
        file_name=f"{status}.md",
        file_type="md",
        source_id=source.id if source else None,
    )
    db_session.add(task)
    db_session.flush()
    return task


# --- 4 status-guard rejection paths ---


@pytest.mark.parametrize("running_status", ["syncing", "parsing", "indexing"])
def test_retry_rejects_running_with_409(client, db_session, running_status):
    _clean_ingest(db_session)
    task = _make_task(db_session, running_status)

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 409, response.text
    body = response.json()
    detail = body["detail"]
    assert detail["code"] == "task_running"
    assert detail["current_status"] == running_status
    assert "retry" in detail["message"]


@pytest.mark.parametrize("queued_status", ["queued", "queued_for_indexing"])
def test_retry_rejects_queued_with_409(client, db_session, queued_status):
    _clean_ingest(db_session)
    task = _make_task(db_session, queued_status)

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "task_queued"
    assert detail["current_status"] == queued_status


@pytest.mark.parametrize("non_terminal", ["uploading", "chunked", "completed"])
def test_retry_rejects_non_retriable_with_409(client, db_session, non_terminal):
    _clean_ingest(db_session)
    task = _make_task(db_session, non_terminal)

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "task_not_retriable"
    assert detail["current_status"] == non_terminal


def test_retry_rejects_within_cooldown_with_429(client, db_session):
    """Just-failed task (updated_at = now) must be rejected with 429 +
    Retry-After header. Pins the 2026-04-24 RCA fix."""
    _clean_ingest(db_session)
    task = _make_task(db_session, "failed")
    # Force updated_at to NOW so cooldown is fully in effect
    task.updated_at = datetime.now(timezone.utc)
    db_session.flush()

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 429, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "retry_cooldown"
    assert detail["current_status"] == "failed"
    assert detail["retry_after_seconds"] >= 1
    # Frontend reads this header for countdown
    assert "Retry-After" in response.headers


def test_retry_succeeds_after_cooldown_window(client, db_session):
    """Task that failed >cooldown ago must be retriable."""
    _clean_ingest(db_session)
    task = _make_task(db_session, "failed")
    # 5 min ago — well past 60s default cooldown
    task.updated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db_session.flush()

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["error_message"] is None


def test_retry_deleted_skips_cooldown(client, db_session):
    """`deleted` is a user action (not failure) — no cooldown applies."""
    _clean_ingest(db_session)
    task = _make_task(db_session, "deleted")
    # updated_at = NOW (just deleted) — cooldown should NOT block
    task.updated_at = datetime.now(timezone.utc)
    db_session.flush()

    response = client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"


def test_retry_rejection_writes_audit_log(client, db_session):
    """Rejected retries must be auditable so we can spot users hammering."""
    _clean_ingest(db_session)
    task = _make_task(db_session, "indexing")

    audit_before = db_session.execute(
        sql_text("SELECT COUNT(*) FROM audit_logs WHERE action='retry_rejected'")
    ).scalar()

    client.post(f"/api/v1/ingest-tasks/{task.id}/retry")

    audit_after = db_session.execute(
        sql_text("SELECT COUNT(*) FROM audit_logs WHERE action='retry_rejected'")
    ).scalar()

    assert audit_after == audit_before + 1


# --- chunks_indexed live progress (P0) ---


def test_chunks_indexed_only_populated_during_indexing(client, db_session):
    """For status != indexing the field is null; for indexing it's a live
    COUNT of committed chunks under task.source_id."""
    _clean_ingest(db_session)
    source = Source(type="document", title="progress.md")
    db_session.add(source)
    db_session.flush()

    # 3 chunks committed so far
    for i in range(3):
        db_session.add(
            Chunk(source_id=source.id, content=f"c{i}", embedding=_zero_vec())
        )
    db_session.flush()

    indexing_task = _make_task(db_session, "indexing", source=source)
    indexing_task.chunk_count = 8  # planned total
    db_session.flush()

    response = client.get(f"/api/v1/ingest-tasks/{indexing_task.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "indexing"
    assert body["chunks_indexed"] == 3
    assert body["chunk_count"] == 8


def test_chunks_indexed_is_null_for_completed(client, db_session):
    _clean_ingest(db_session)
    source = Source(type="document", title="done.md")
    db_session.add(source)
    db_session.flush()
    db_session.add(Chunk(source_id=source.id, content="c", embedding=_zero_vec()))
    db_session.flush()

    task = _make_task(db_session, "completed", source=source)
    task.chunk_count = 1
    db_session.flush()

    response = client.get(f"/api/v1/ingest-tasks/{task.id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chunks_indexed"] is None
    assert body["chunk_count"] == 1
