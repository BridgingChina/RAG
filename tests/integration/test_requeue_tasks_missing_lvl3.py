"""Integration tests for ``scripts/requeue_tasks_missing_lvl3.py`` helpers.

Pin the bug-fingerprint query and the re-queue state transition that the
one-shot Phase 3 recovery script relies on. These go red if anyone later
tightens/loosens the fingerprint or changes the retry-cleanup contract.

The task fixture uses raw SQL insert because local dev DBs that were
created before the Phase 2 auth rewrite may still have
``ingest_tasks.created_by`` as UUID (the column is now VARCHAR in the
model and in prod v10). Going through the ORM triggers a
``::VARCHAR`` cast that the drifted local column rejects. Raw SQL with
an explicit NULL sidesteps the type mismatch entirely.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, Source
from app.models.ingest_task import IngestTask
from scripts.requeue_tasks_missing_lvl3 import (
    find_affected_tasks,
    requeue_task,
)


def _zero_emb() -> list[float]:
    return [0.0] * EMBEDDING_DIM


def _make_task(
    db_session,
    *,
    status: str = "completed",
    updated_offset_days: int = 0,
) -> IngestTask:
    source = Source(type="note", title="rq_src")
    db_session.add(source)
    db_session.flush()

    task_id = uuid.uuid4()
    updated_at = datetime.now(timezone.utc) + timedelta(days=updated_offset_days)
    db_session.execute(
        text(
            "INSERT INTO ingest_tasks "
            "(id, status, file_name, file_type, source_id, chunk_count, "
            "r2_raw_key, image_count, updated_at, created_at) "
            "VALUES (:id, :status, :fn, :ft, :sid, 1, :r2, 0, :updated_at, now())"
        ),
        {
            "id": task_id,
            "status": status,
            "fn": "rq_doc.pdf",
            "ft": "pdf",
            "sid": source.id,
            "r2": "r2/raw/rq_doc.pdf",
            "updated_at": updated_at,
        },
    )
    db_session.flush()

    task = db_session.get(IngestTask, task_id)
    assert task is not None
    return task


def test_finds_task_with_bug_fingerprint(db_session):
    task = _make_task(db_session)
    db_session.add(
        Chunk(
            source_id=task.source_id,
            content="fingerprint-positive",
            lvl1="形制与技术",
            lvl2="结构体系",
            lvl3=None,
            knowledge_point_id=None,
            embedding=_zero_emb(),
        )
    )
    db_session.flush()

    since = datetime.now(timezone.utc) - timedelta(days=365)
    results = find_affected_tasks(db_session, since, None)

    assert len(results) == 1
    assert results[0][0].id == task.id
    assert results[0][1] == 1


def test_ignores_chunks_with_lvl1_lvl2_also_null(db_session):
    """Legitimate un-classifiable chunks have lvl1/lvl2 NULL too — not the bug."""
    task = _make_task(db_session)
    db_session.add(
        Chunk(
            source_id=task.source_id,
            content="legit-null",
            lvl1=None,
            lvl2=None,
            lvl3=None,
            knowledge_point_id=None,
            embedding=_zero_emb(),
        )
    )
    db_session.flush()

    since = datetime.now(timezone.utc) - timedelta(days=365)
    results = find_affected_tasks(db_session, since, None)

    assert results == []


def test_ignores_chunks_with_lvl3_already_set(db_session):
    task = _make_task(db_session)
    db_session.add(
        Chunk(
            source_id=task.source_id,
            content="already-tagged",
            lvl1="形制与技术",
            lvl2="结构体系",
            lvl3="拱桥结构",
            knowledge_point_id=None,
            embedding=_zero_emb(),
        )
    )
    db_session.flush()

    since = datetime.now(timezone.utc) - timedelta(days=365)
    results = find_affected_tasks(db_session, since, None)

    assert results == []


def test_ignores_non_completed_tasks(db_session):
    task = _make_task(db_session, status="failed")
    db_session.add(
        Chunk(
            source_id=task.source_id,
            content="failed-task-chunk",
            lvl1="形制与技术",
            lvl2="结构体系",
            lvl3=None,
            knowledge_point_id=None,
            embedding=_zero_emb(),
        )
    )
    db_session.flush()

    since = datetime.now(timezone.utc) - timedelta(days=365)
    results = find_affected_tasks(db_session, since, None)

    assert results == []


def test_respects_since_cutoff(db_session):
    old_task = _make_task(db_session, updated_offset_days=-30)
    db_session.add(
        Chunk(
            source_id=old_task.source_id,
            content="old-bug-chunk",
            lvl1="形制与技术",
            lvl2="结构体系",
            lvl3=None,
            knowledge_point_id=None,
            embedding=_zero_emb(),
        )
    )
    db_session.flush()

    future_cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    assert find_affected_tasks(db_session, future_cutoff, None) == []


def test_requeue_task_clears_source_and_resets_status(db_session, monkeypatch):
    # audit_logs.user_id suffers the same VARCHAR/UUID drift as ingest_tasks
    # on pre-Phase-2 local DBs. Stub the audit write — the contract under
    # test here is "task + source + chunks reset", not the audit emission
    # which is covered by the /retry endpoint tests separately.
    from app.services.audit_service import AuditService

    monkeypatch.setattr(AuditService, "log", lambda *a, **k: None)

    task = _make_task(db_session)
    source_id = task.source_id
    db_session.add(
        Chunk(
            source_id=source_id,
            content="to-be-wiped",
            lvl1="形制与技术",
            lvl2="结构体系",
            lvl3=None,
            knowledge_point_id=None,
            embedding=_zero_emb(),
        )
    )
    db_session.flush()

    requeue_task(db_session, task)

    assert task.status == "queued"
    assert task.source_id is None
    assert task.chunk_count is None
    assert task.parsed_content is None
    assert task.image_count == 0
    assert task.error_message is None
    assert db_session.get(Source, source_id) is None
    remaining = db_session.query(Chunk).filter(Chunk.source_id == source_id).count()
    assert remaining == 0
