"""Integration test for schema migration v8 → v9.

Validates that migrate_v8_to_v9 adds chunks.knowledge_point_id FK and
backfills it from the existing (lvl1, lvl2, lvl3) → KnowledgePoint
same-name mapping.

v9 is the first step of the lvl3-KP merge refactor; see
docs/plans/2026-04-17-merge-lvl3-kp-design.md Phase 1 Task 2.
"""
from sqlalchemy import text

from app.core.constants import EMBEDDING_DIM
from app.models import Chunk, KnowledgePoint, TaxonomyNode
from scripts.migrate_db import migrate_v8_to_v9


def _ensure_v9_column(db_session) -> None:
    """Make the column available so SQLAlchemy INSERTs (which include the column
    in the SQL because the ORM model declares it) succeed during seed. The real
    test then drops it to simulate v8 before invoking the migration under test.
    """
    db_session.execute(text(
        "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS knowledge_point_id UUID "
        "REFERENCES knowledge_points(id) ON DELETE SET NULL"
    ))
    db_session.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_chunks_knowledge_point_id ON chunks(knowledge_point_id)"
    ))
    db_session.flush()


def _simulate_v8_state(db_session) -> None:
    """Drop the v9 column + index so migrate_v8_to_v9 exercises its DDL path."""
    db_session.execute(text("DROP INDEX IF EXISTS ix_chunks_knowledge_point_id"))
    db_session.execute(text("ALTER TABLE chunks DROP COLUMN IF EXISTS knowledge_point_id"))
    db_session.flush()


def _empty_embedding() -> list[float]:
    return [0.0] * EMBEDDING_DIM


def test_migrate_v8_to_v9_creates_column_index_fk_and_backfills(db_session, test_source):
    _ensure_v9_column(db_session)
    tn = TaxonomyNode(lvl1="v9_l1", lvl2="v9_l2", lvl3="v9_l3")
    db_session.add(tn)
    db_session.flush()

    kp = KnowledgePoint(name="v9_l3", lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()

    chunk_match_a = Chunk(
        source_id=test_source.id, content="v9-match-a",
        lvl1="v9_l1", lvl2="v9_l2", lvl3="v9_l3",
        embedding=_empty_embedding(),
    )
    chunk_match_b = Chunk(
        source_id=test_source.id, content="v9-match-b",
        lvl1="v9_l1", lvl2="v9_l2", lvl3="v9_l3",
        embedding=_empty_embedding(),
    )
    chunk_no_lvl3 = Chunk(
        source_id=test_source.id, content="v9-no-lvl3",
        lvl1="v9_l1", lvl2="v9_l2", lvl3=None,
        embedding=_empty_embedding(),
    )
    chunk_unknown_lvl3 = Chunk(
        source_id=test_source.id, content="v9-unknown",
        lvl1="v9_l1", lvl2="v9_l2", lvl3="does_not_exist",
        embedding=_empty_embedding(),
    )
    db_session.add_all([chunk_match_a, chunk_match_b, chunk_no_lvl3, chunk_unknown_lvl3])
    db_session.flush()

    match_a_id = chunk_match_a.id
    match_b_id = chunk_match_b.id
    no_lvl3_id = chunk_no_lvl3.id
    unknown_id = chunk_unknown_lvl3.id

    # Simulate v8 state: the column and index don't exist yet.
    _simulate_v8_state(db_session)

    migrate_v8_to_v9(db_session.connection())

    col_row = db_session.execute(text(
        "SELECT data_type, is_nullable FROM information_schema.columns "
        "WHERE table_name='chunks' AND column_name='knowledge_point_id'"
    )).fetchone()
    assert col_row is not None, "knowledge_point_id column was not created"
    assert col_row[0] == "uuid"
    assert col_row[1] == "YES"

    idx_row = db_session.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename='chunks' AND indexname='ix_chunks_knowledge_point_id'"
    )).fetchone()
    assert idx_row is not None, "ix_chunks_knowledge_point_id index was not created"

    fk_row = db_session.execute(text(
        """
        SELECT rc.delete_rule
        FROM information_schema.referential_constraints rc
        JOIN information_schema.key_column_usage kcu
          ON rc.constraint_name = kcu.constraint_name
        WHERE kcu.table_name = 'chunks' AND kcu.column_name = 'knowledge_point_id'
        """
    )).fetchone()
    assert fk_row is not None, "FK constraint missing on chunks.knowledge_point_id"
    assert fk_row[0] == "SET NULL"

    rows = db_session.execute(text(
        "SELECT id, knowledge_point_id FROM chunks "
        "WHERE id IN (:a, :b, :c, :d)"
    ).bindparams(a=match_a_id, b=match_b_id, c=no_lvl3_id, d=unknown_id)).fetchall()
    by_id = {row[0]: row[1] for row in rows}
    assert by_id[match_a_id] == kp.id, "matching chunk A should be backfilled"
    assert by_id[match_b_id] == kp.id, "matching chunk B should be backfilled"
    assert by_id[no_lvl3_id] is None, "chunk without lvl3 must remain NULL"
    assert by_id[unknown_id] is None, "chunk with unknown lvl3 label must remain NULL"


def test_migrate_v8_to_v9_is_idempotent(db_session, test_source):
    _ensure_v9_column(db_session)
    tn = TaxonomyNode(lvl1="v9i_l1", lvl2="v9i_l2", lvl3="v9i_l3")
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="v9i_l3", lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()

    chunk = Chunk(
        source_id=test_source.id, content="v9-idem",
        lvl1="v9i_l1", lvl2="v9i_l2", lvl3="v9i_l3",
        embedding=_empty_embedding(),
    )
    db_session.add(chunk)
    db_session.flush()
    chunk_id = chunk.id

    _simulate_v8_state(db_session)

    conn = db_session.connection()
    migrate_v8_to_v9(conn)
    # Second run must not error and must not flip the value back to NULL.
    migrate_v8_to_v9(conn)

    kp_id = db_session.execute(text(
        "SELECT knowledge_point_id FROM chunks WHERE id = :cid"
    ).bindparams(cid=chunk_id)).scalar_one()
    assert kp_id == kp.id
