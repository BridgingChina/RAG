import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Base, Bridge, Chunk, Source
from app.services.tokenizer import Tokenizer


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(settings.database_url)

    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        Base.metadata.create_all(engine)
    except OperationalError as e:
        pytest.skip(
            "PostgreSQL+pgvector test DB not available. "
            "Start it with `docker compose up -d db` and retry."
        )
    return engine


@pytest.fixture
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    # Ensure a clean DB for each test without destroying any pre-existing data.
    session.execute(text("DELETE FROM chunks"))
    session.execute(text("DELETE FROM sources"))
    session.execute(text("DELETE FROM bridges"))
    session.execute(text("DELETE FROM taxonomy_nodes"))
    session.flush()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def tokenizer():
    return Tokenizer()


@pytest.fixture
def test_source(db_session):
    source = Source(type="note", title="Test Source")
    db_session.add(source)
    db_session.flush()
    return source


@pytest.fixture
def test_bridges(db_session):
    target = Bridge(
        name="赵州桥",
        location="河北 赵县 华北",
        era="隋唐",
        bridge_type="石拱桥",
        material="石",
    )
    candidate1 = Bridge(
        name="卢沟桥",
        location="北京 华北",
        era="隋唐",
        bridge_type="石拱桥",
        material="石",
    )
    candidate2 = Bridge(
        name="安济桥",
        location="山东 华北",
        era="隋唐",
        bridge_type="石拱桥",
        material="石",
    )
    other = Bridge(
        name="泸定桥",
        location="四川 西南",
        era="明清",
        bridge_type="悬索桥",
        material="铁",
    )

    db_session.add_all([target, candidate1, candidate2, other])
    db_session.flush()
    return {
        "target": target,
        "candidate1": candidate1,
        "candidate2": candidate2,
        "other": other,
    }


@pytest.fixture
def chunk_factory(db_session, test_source, tokenizer):
    def make_chunk(
        *,
        content: str,
        embedding: list[float],
        bridge_id: int | None = None,
        lvl1: str | None = "形制与技术",
        search_text: str | None = None,
    ) -> Chunk:
        chunk = Chunk(
            source_id=test_source.id,
            content=content,
            lvl1=lvl1,
            bridge_id=bridge_id,
            embedding=embedding,
            search_text=search_text,
        )
        db_session.add(chunk)
        db_session.flush()

        # Populate tsvector for FTS queries.
        tsvector_text = tokenizer.to_tsvector_text(search_text or content)
        db_session.execute(
            text(
                "UPDATE chunks SET tsv = to_tsvector('simple', :tsv_text) WHERE id = :id"
            ),
            {"tsv_text": tsvector_text, "id": chunk.id},
        )
        db_session.flush()
        return chunk

    return make_chunk


@pytest.fixture
def test_chunks(test_bridges, chunk_factory):
    def emb(v0: float, v1: float = 0.0) -> list[float]:
        vec = [0.0] * 2048
        vec[0] = v0
        vec[1] = v1
        return vec

    target = test_bridges["target"]
    candidate1 = test_bridges["candidate1"]
    candidate2 = test_bridges["candidate2"]

    chunks: dict[str, list[Chunk]] = {
        "anchor": [],
        "concept": [],
        "analogy_candidate1": [],
        "analogy_candidate2": [],
    }

    # Anchor chunks (>= 6)
    for i in range(8):
        chunks["anchor"].append(
            chunk_factory(
                content=f"赵州桥 结构要点 {i}（石拱桥）",
                bridge_id=target.id,
                embedding=emb(1.0, 0.0),
            )
        )

    # Concept chunks (bridge_id is NULL, >= 2)
    for i in range(3):
        chunks["concept"].append(
            chunk_factory(
                content=f"石拱桥 通用知识 {i}",
                bridge_id=None,
                embedding=emb(0.5, 0.5),
            )
        )

    # Analogy chunks across two candidate bridges
    for i in range(3):
        chunks["analogy_candidate1"].append(
            chunk_factory(
                content=f"卢沟桥 桥梁案例 {i}（石拱桥）",
                bridge_id=candidate1.id,
                embedding=emb(0.9, 0.1),
            )
        )
        chunks["analogy_candidate2"].append(
            chunk_factory(
                content=f"安济桥 桥梁案例 {i}（石拱桥）",
                bridge_id=candidate2.id,
                embedding=emb(0.85, 0.15),
            )
        )

    return chunks
