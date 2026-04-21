"""Integration tests for schema migration v12 → v13.

Exercises the real ``migrate_v12_to_v13`` function against a running
PostgreSQL instance. Uses a ``real_db`` pattern (rather than the
session-rollback ``db_session`` from conftest) so the migration's CREATE
TABLE / INSERT statements actually persist long enough to be inspected
and so we can verify the FK RESTRICT constraint raises IntegrityError
on DELETE.

Every test cleans up after itself: each test simulates v12 state by
dropping the three v13 tables + the v13 schema_version row at fixture
entry, then re-runs the migration.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.database import SessionLocal
from scripts.migrate_db import migrate_v12_to_v13


@pytest.fixture
def real_db(db_engine):
    """Real SessionLocal with v13 rollback + re-migration on entry.

    Like ``tests/integration/test_ingest_scheduler_e2e.py::real_db`` this
    commits real data (so ON DELETE RESTRICT on a separate transaction
    fires) and cleans up on teardown.

    Each test starts with a fresh migration: the three v13 tables are
    dropped plus the v13 schema_version row, then the migration is run
    again inside the test body or at fixture entry.
    """
    from app.models import Base

    Base.metadata.create_all(db_engine)

    try:
        test_db = SessionLocal()
        test_db.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(
            "PostgreSQL test DB not available. "
            "Start it with `docker compose up -d db` and retry."
        )

    def _rollback_v13(db):
        db.execute(text("DROP TABLE IF EXISTS llm_task_routes CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS llm_provider_models CASCADE"))
        db.execute(text("DROP TABLE IF EXISTS llm_providers CASCADE"))
        db.execute(text("DELETE FROM schema_version WHERE version = 13"))
        db.commit()

    # Fresh v12 state at entry
    _rollback_v13(test_db)
    try:
        yield test_db
    finally:
        _rollback_v13(test_db)
        test_db.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


def test_v13_creates_three_tables(real_db):
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    existing = set(real_db.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' "
        "AND table_name IN ('llm_providers', 'llm_provider_models', 'llm_task_routes')"
    )).scalars().all())
    assert existing == {"llm_providers", "llm_provider_models", "llm_task_routes"}

    # Spot-check the expected column lists.
    providers_cols = set(real_db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'llm_providers'"
    )).scalars().all())
    assert providers_cols == {
        "id", "name", "kind", "base_url", "api_key_env", "extra_headers",
        "enabled", "timeout_read", "last_tested_at", "last_test_ok",
        "last_test_error", "created_at", "updated_at",
    }

    models_cols = set(real_db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'llm_provider_models'"
    )).scalars().all())
    assert models_cols == {
        "id", "provider_id", "model_id", "display_name", "kind",
        "context_window", "extra", "fetched_at",
    }

    routes_cols = set(real_db.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'llm_task_routes'"
    )).scalars().all())
    assert routes_cols == {
        "task_key", "provider_id", "model_id", "updated_at", "updated_by",
    }


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------


def test_v13_seeds_zhipu_provider(real_db):
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    rows = real_db.execute(text(
        "SELECT name, kind, api_key_env, base_url FROM llm_providers"
    )).all()
    assert len(rows) == 1
    name, kind, api_key_env, base_url = rows[0]
    assert name == "智谱 AI（默认）"
    assert kind == "zhipu"
    assert api_key_env == "ZHIPU_API_KEY"
    assert base_url == "https://open.bigmodel.cn/api/paas/v4"


def test_v13_seeds_seven_task_routes(real_db):
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    rows = real_db.execute(text(
        "SELECT task_key, provider_id, model_id FROM llm_task_routes"
    )).all()
    assert len(rows) == 7

    task_keys = {r[0] for r in rows}
    assert task_keys == {
        "qa_generation",
        "qa_facet_extraction",
        "ingest_tagger",
        "ingest_context_enricher",
        "ingest_bridge_linker",
        "content_generation",
        "translation",
    }

    # All routes reference the seeded Zhipu provider.
    zhipu_id = real_db.execute(text(
        "SELECT id FROM llm_providers WHERE name = '智谱 AI（默认）'"
    )).scalar()
    for _, provider_id, _ in rows:
        assert provider_id == zhipu_id

    # Spot-check a couple of specific model assignments.
    model_map = {r[0]: r[2] for r in rows}
    assert model_map["qa_generation"] == "glm-4.7"
    assert model_map["qa_facet_extraction"] == "glm-4-flash"
    assert model_map["translation"] == "glm-4.7"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_v13_is_idempotent(real_db):
    """Running the migration twice must not raise (seed uses ON CONFLICT)."""
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    # Second run — CREATE TABLE IF NOT EXISTS + ON CONFLICT DO NOTHING
    # make this a no-op.
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    # Counts should stay at 1 provider + 7 routes.
    assert real_db.execute(text("SELECT COUNT(*) FROM llm_providers")).scalar() == 1
    assert real_db.execute(text("SELECT COUNT(*) FROM llm_task_routes")).scalar() == 7


# ---------------------------------------------------------------------------
# FK semantics
# ---------------------------------------------------------------------------


def test_v13_fk_restrict_prevents_provider_delete_when_route_exists(real_db):
    """The seeded Zhipu provider is referenced by 7 task routes; DELETE
    should fail with IntegrityError (foreign_key_violation)."""
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    zhipu_id = real_db.execute(text(
        "SELECT id FROM llm_providers WHERE name = '智谱 AI（默认）'"
    )).scalar()

    with pytest.raises(IntegrityError):
        real_db.execute(
            text("DELETE FROM llm_providers WHERE id = :id"),
            {"id": zhipu_id},
        )
        real_db.commit()
    real_db.rollback()

    # The provider must still be there after the rejected delete.
    still_there = real_db.execute(text(
        "SELECT COUNT(*) FROM llm_providers WHERE id = :id"
    ), {"id": zhipu_id}).scalar()
    assert still_there == 1


def test_v13_cascade_deletes_models_when_provider_deleted(real_db):
    """A provider with NO routes can be deleted, and its cached model rows
    go with it (llm_provider_models.provider_id is ON DELETE CASCADE).

    Uses a freshly-inserted 'Test Provider Delete' so the seeded Zhipu
    provider (which has 7 routes) is not affected by the RESTRICT FK.
    """
    migrate_v12_to_v13(real_db.connection())
    real_db.commit()

    new_id = real_db.execute(text("""
        INSERT INTO llm_providers (name, kind, base_url, api_key_env)
        VALUES ('Test Provider Delete', 'openai_compat',
                'https://example.invalid/v1', 'TEST_PROVIDER_DELETE_KEY')
        RETURNING id
    """)).scalar()
    real_db.commit()

    # Add a cached model row tied to the new provider.
    real_db.execute(
        text("""
            INSERT INTO llm_provider_models (provider_id, model_id, display_name, kind)
            VALUES (:pid, 'test-model-1', 'Test Model 1', 'chat')
        """),
        {"pid": new_id},
    )
    real_db.commit()

    # Sanity: the model row exists before delete.
    model_count_before = real_db.execute(text(
        "SELECT COUNT(*) FROM llm_provider_models WHERE provider_id = :pid"
    ), {"pid": new_id}).scalar()
    assert model_count_before == 1

    # Delete the provider — should cascade to the model row.
    real_db.execute(text("DELETE FROM llm_providers WHERE id = :id"), {"id": new_id})
    real_db.commit()

    model_count_after = real_db.execute(text(
        "SELECT COUNT(*) FROM llm_provider_models WHERE provider_id = :pid"
    ), {"pid": new_id}).scalar()
    assert model_count_after == 0

    provider_count_after = real_db.execute(text(
        "SELECT COUNT(*) FROM llm_providers WHERE id = :id"
    ), {"id": new_id}).scalar()
    assert provider_count_after == 0
