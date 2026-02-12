import pytest

from app.core.constants import EMBEDDING_DIM
from app.models import Bridge, Chunk, ChunkBridgeLink, Source


def test_create_schema_version():
    """Test creating schema version record"""
    from app.models.schema_version import SchemaVersion
    from datetime import datetime

    version = SchemaVersion(
        version=1,
        description="Initial schema"
    )

    assert version.version == 1
    assert version.description == "Initial schema"
    assert isinstance(version.created_at, datetime) or version.created_at is None


def test_create_bridge(db_session):
    bridge = Bridge(name="赵州桥", location="河北赵县")
    db_session.add(bridge)
    db_session.flush()

    assert bridge.id is not None
    assert bridge.name == "赵州桥"


def test_create_chunk_with_embedding(db_session):
    source = Source(type="note", title="Test Note")
    db_session.add(source)
    db_session.flush()

    embedding = [0.1] * EMBEDDING_DIM
    chunk = Chunk(
        source_id=source.id,
        content="赵州桥是一座石拱桥",
        lvl1="形制与技术",
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.flush()

    assert chunk.id is not None
    assert len(chunk.embedding) == EMBEDDING_DIM
    assert chunk.bridge_binding_status == "none"


def test_create_chunk_bridge_link(db_session):
    source = Source(type="note", title="Link Source")
    db_session.add(source)
    db_session.flush()

    bridge = Bridge(name="测试桥")
    db_session.add(bridge)
    db_session.flush()

    chunk = Chunk(
        source_id=source.id,
        content="测试段落",
        embedding=[0.1] * EMBEDDING_DIM,
        bridge_id=bridge.id,
        bridge_binding_status="primary",
    )
    db_session.add(chunk)
    db_session.flush()

    link = ChunkBridgeLink(
        chunk_id=chunk.id,
        bridge_id=bridge.id,
        role="primary",
        confidence=1.0,
        method="hint",
    )
    db_session.add(link)
    db_session.flush()

    assert link.id is not None
    assert link.role == "primary"
