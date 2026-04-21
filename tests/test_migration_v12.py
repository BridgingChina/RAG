"""Schema v11→v12 migration tests (i18n Phase 3).

Skipped when Postgres is unavailable — the migration function is exercised
by an integration-style test, but the schema-version constant + migration
dict registration are checked unconditionally.
"""
from __future__ import annotations

import pytest

from app.core.database import LATEST_SCHEMA_VERSION
from scripts import migrate_db


def test_v11_to_v12_migration_registered():
    """The migrate_db MIGRATIONS dict must have an entry for every prior
    version."""
    assert 11 in migrate_db.MIGRATIONS
    assert callable(migrate_db.MIGRATIONS[11])
    # And every integer in [1, LATEST) must map to a migrator.
    for v in range(1, LATEST_SCHEMA_VERSION):
        assert v in migrate_db.MIGRATIONS, f"Missing migration for v{v} -> v{v+1}"


def test_migrate_db_has_v11_to_v12_fn():
    assert hasattr(migrate_db, "migrate_v11_to_v12")


def test_translation_review_model_imports_cleanly():
    """Regression — fresh DB inits must succeed, so the new model's metadata
    has to be importable by ``app.models.Base``."""
    from app.models import TranslationReview  # noqa: F401
    from app.models.translation_review import (
        TRANSLATION_STATUS_AI_GENERATED,
        TRANSLATION_STATUS_HUMAN_REVIEWED,
        TRANSLATION_STATUS_PENDING_AI,
        TRANSLATION_STATUS_REJECTED,
        VALID_TRANSLATION_STATUSES,
    )
    assert VALID_TRANSLATION_STATUSES == {
        TRANSLATION_STATUS_PENDING_AI,
        TRANSLATION_STATUS_AI_GENERATED,
        TRANSLATION_STATUS_HUMAN_REVIEWED,
        TRANSLATION_STATUS_REJECTED,
    }


@pytest.mark.integration
def test_v11_to_v12_migration_live_db(db_session):
    """Live-DB assertion that the migration adds the new columns + table.

    Skipped when Postgres isn't running (the ``db_session`` fixture calls
    ``pytest.skip`` in its session-scoped parent).
    """
    from sqlalchemy import text

    # Columns on existing tables.
    expected = [
        ("bridges", "name_en"),
        ("bridges", "description_en"),
        ("knowledge_points", "name_en"),
        ("knowledge_points", "summary_en"),
        ("flashcards", "front_title_en"),
        ("flashcards", "back_answer_en"),
        ("taxonomy_nodes", "name_en"),
        ("chunks", "cached_en_summary"),
        ("chunks", "cached_en_summary_at"),
    ]
    for table, column in expected:
        got = db_session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).scalar_one_or_none()
        assert got == column, f"{table}.{column} missing after migration"

    # New table exists and has expected columns.
    translation_cols = set(db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'translation_reviews'"
    )).scalars().all())
    required = {
        "id", "table_name", "row_id", "field_name", "source_text",
        "ai_translation", "reviewed_translation", "status",
        "reviewed_by", "reviewed_at", "created_at",
    }
    assert required.issubset(translation_cols), (
        f"translation_reviews missing columns: {required - translation_cols}"
    )
