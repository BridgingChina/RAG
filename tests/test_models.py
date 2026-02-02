import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.models import Base, Bridge, Chunk, Source, TaxonomyNode


@pytest.fixture
def db_session():
    engine = create_engine("postgresql+psycopg://bridge:bridge@localhost:5433/bridge_rag")

    # Enable pgvector extension
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session
        session.rollback()


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

    embedding = [0.1] * 1024
    chunk = Chunk(
        source_id=source.id,
        content="赵州桥是一座石拱桥",
        lvl1="形制与技术",
        embedding=embedding,
    )
    db_session.add(chunk)
    db_session.flush()

    assert chunk.id is not None
    assert len(chunk.embedding) == 1024
