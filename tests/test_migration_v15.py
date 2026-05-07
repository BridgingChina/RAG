"""Schema v14→v15 migration tests (inline translation review).

Mirrors the structure of ``test_migration_v12.py``: schema-version constant
+ MIGRATIONS dict registration are checked unconditionally; live-DB column
existence is gated by ``@pytest.mark.integration`` and skipped via the
``db_session`` fixture's parent when Postgres isn't running.
"""
from __future__ import annotations

import pytest

from app.core.database import LATEST_SCHEMA_VERSION
from scripts import migrate_db


def test_v14_to_v15_migration_registered():
    """The migrate_db MIGRATIONS dict must have an entry for every prior version."""
    assert 14 in migrate_db.MIGRATIONS
    assert callable(migrate_db.MIGRATIONS[14])
    for v in range(1, LATEST_SCHEMA_VERSION):
        assert v in migrate_db.MIGRATIONS, f"Missing migration for v{v} -> v{v+1}"


def test_migrate_db_has_v14_to_v15_fn():
    assert hasattr(migrate_db, "migrate_v14_to_v15")


def test_latest_schema_version_is_15():
    assert LATEST_SCHEMA_VERSION == 15


def test_key_point_model_has_en_translation_columns():
    """Phase v15: knowledge_point_key_points carries summary_en + explanation_en."""
    from app.models.knowledge_point_key_point import KnowledgePointKeyPoint

    assert "summary_en" in KnowledgePointKeyPoint.__table__.columns
    assert "explanation_en" in KnowledgePointKeyPoint.__table__.columns
    # Both nullable — populated lazily via the translation审校 flow
    assert KnowledgePointKeyPoint.__table__.columns["summary_en"].nullable
    assert KnowledgePointKeyPoint.__table__.columns["explanation_en"].nullable


@pytest.mark.integration
def test_v14_to_v15_migration_live_db(db_session):
    """Live-DB assertion that the migration adds the two columns idempotently."""
    from sqlalchemy import text

    expected = [
        ("knowledge_point_key_points", "summary_en"),
        ("knowledge_point_key_points", "explanation_en"),
    ]
    for table, column in expected:
        got = db_session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar_one_or_none()
        assert got == column, f"{table}.{column} missing after migration"
