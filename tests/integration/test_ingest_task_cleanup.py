"""Integration test for _cleanup_task_data FK ordering fix (issue #148 Bug #2).

These tests require a running PostgreSQL+pgvector instance.
They will be skipped if the DB is unavailable (see tests/conftest.py).
"""
import uuid

import pytest
from sqlalchemy import text as sql_text

from app.api.v1.ingest_tasks import _cleanup_task_data
from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, ChunkBridgeLink, Source
from app.models.ingest_task import IngestTask


def _zero_vec() -> list[float]:
    return [0.0] * EMBEDDING_DIM


@pytest.fixture
def _task_with_source(db_session, test_bridges):
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


def test_cleanup_task_data_removes_source_chunks_and_links(db_session, _task_with_source):
    """_cleanup_task_data should remove source + chunks + links without FK violation."""
    fixture = _task_with_source
    task = fixture["task"]
    source_id = fixture["source"].id
    chunk_ids = [c.id for c in fixture["chunks"]]

    # This is the regression: pre-fix, delete Source threw FK violation
    # because task.source_id was still dirty-referencing the source.
    _cleanup_task_data(db_session, task)
    # Must be able to commit the transaction (this was the actual failure mode)
    db_session.commit()

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
    """Task without source_id should be handled gracefully (no-op)."""
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
    db_session.commit()

    assert task.source_id is None
    assert (
        db_session.query(IngestTask).filter(IngestTask.id == task.id).count() == 1
    )
