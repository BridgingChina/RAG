"""Integration test for schema migration v9 → v10.

Validates that migrate_v9_to_v10 adds knowledge_points.lvl1 / lvl2 columns,
the composite index, and backfills the two columns from the
taxonomy_nodes row the KP points at.
"""
from sqlalchemy import text

from app.models import KnowledgePoint, TaxonomyNode
from scripts.migrate_db import migrate_v9_to_v10


def _ensure_v10_columns(db_session) -> None:
    db_session.execute(text(
        "ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS lvl1 VARCHAR(100)"
    ))
    db_session.execute(text(
        "ALTER TABLE knowledge_points ADD COLUMN IF NOT EXISTS lvl2 VARCHAR(100)"
    ))
    db_session.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_kp_lvl1_lvl2 ON knowledge_points(lvl1, lvl2)"
    ))
    db_session.flush()


def _simulate_v9_state(db_session) -> None:
    db_session.execute(text("DROP INDEX IF EXISTS ix_kp_lvl1_lvl2"))
    db_session.execute(text("ALTER TABLE knowledge_points DROP COLUMN IF EXISTS lvl1"))
    db_session.execute(text("ALTER TABLE knowledge_points DROP COLUMN IF EXISTS lvl2"))
    db_session.flush()


def test_v10_adds_columns_index_and_backfills(db_session):
    _ensure_v10_columns(db_session)

    tn = TaxonomyNode(lvl1="v10_l1", lvl2="v10_l2", lvl3="v10_l3")
    db_session.add(tn)
    db_session.flush()

    kp = KnowledgePoint(name="v10_l3_kp", lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()
    kp_id = kp.id

    _simulate_v9_state(db_session)

    migrate_v9_to_v10(db_session.connection())

    col_rows = db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='knowledge_points' AND column_name IN ('lvl1','lvl2')"
    )).fetchall()
    assert {r[0] for r in col_rows} == {"lvl1", "lvl2"}

    idx = db_session.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename='knowledge_points' AND indexname='ix_kp_lvl1_lvl2'"
    )).fetchone()
    assert idx is not None

    row = db_session.execute(text(
        "SELECT lvl1, lvl2 FROM knowledge_points WHERE id = :id"
    ).bindparams(id=kp_id)).fetchone()
    assert row == ("v10_l1", "v10_l2")


def test_v10_is_idempotent(db_session):
    _ensure_v10_columns(db_session)

    tn = TaxonomyNode(lvl1="v10i_l1", lvl2="v10i_l2", lvl3="v10i_l3")
    db_session.add(tn)
    db_session.flush()
    kp = KnowledgePoint(name="v10i_l3_kp", lvl1=tn.lvl1, lvl2=tn.lvl2, taxonomy_node_id=tn.id)
    db_session.add(kp)
    db_session.flush()
    kp_id = kp.id

    _simulate_v9_state(db_session)

    conn = db_session.connection()
    migrate_v9_to_v10(conn)
    migrate_v9_to_v10(conn)

    row = db_session.execute(text(
        "SELECT lvl1, lvl2 FROM knowledge_points WHERE id = :id"
    ).bindparams(id=kp_id)).fetchone()
    assert row == ("v10i_l1", "v10i_l2")
