"""Unit tests for LLM routing ORM models (schema v13).

Pure schema inspection — no DB required. Verifies column lists, FK cascade
behaviour, and CHECK constraint contents match the SQL spec in
``scripts/migrate_db.py::migrate_v12_to_v13``.
"""
from sqlalchemy import CheckConstraint

from app.models.llm import LLMProviderModel, LLMProviderRow, LLMTaskRoute


def test_llm_provider_row_has_expected_columns():
    """LLMProviderRow columns match the v13 SQL spec exactly."""
    assert LLMProviderRow.__tablename__ == "llm_providers"
    columns = {c.name for c in LLMProviderRow.__table__.columns}
    assert columns == {
        "id",
        "name",
        "kind",
        "base_url",
        "api_key_env",
        "extra_headers",
        "enabled",
        "timeout_read",
        "last_tested_at",
        "last_test_ok",
        "last_test_error",
        "created_at",
        "updated_at",
    }


def test_llm_provider_model_fk_cascade():
    """llm_provider_models.provider_id has exactly one FK to llm_providers.id
    with ON DELETE CASCADE (provider removal wipes its cached model list)."""
    assert LLMProviderModel.__tablename__ == "llm_provider_models"
    columns = {c.name for c in LLMProviderModel.__table__.columns}
    assert columns == {
        "id",
        "provider_id",
        "model_id",
        "display_name",
        "kind",
        "context_window",
        "extra",
        "fetched_at",
    }

    fks = list(LLMProviderModel.__table__.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "llm_providers"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_llm_task_route_fk_restrict():
    """llm_task_routes.provider_id has exactly one FK to llm_providers.id
    with ON DELETE RESTRICT (an in-use provider cannot be deleted)."""
    assert LLMTaskRoute.__tablename__ == "llm_task_routes"
    columns = {c.name for c in LLMTaskRoute.__table__.columns}
    assert columns == {
        "task_key",
        "provider_id",
        "model_id",
        # v14 (2026-05-07): per-task payload knobs (e.g. reasoning toggle)
        "model_params",
        "updated_at",
        "updated_by",
    }

    fks = list(LLMTaskRoute.__table__.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "llm_providers"
    assert fk.column.name == "id"
    assert fk.ondelete == "RESTRICT"


def test_llm_providers_kind_check_constraint_names_three_kinds():
    """ck_llm_providers_kind restricts kind to the three supported provider
    families: zhipu, openai_compat, minimax."""
    check_constraints = [
        c for c in LLMProviderRow.__table__.constraints
        if isinstance(c, CheckConstraint)
    ]
    named = [c for c in check_constraints if c.name == "ck_llm_providers_kind"]
    assert len(named) == 1, (
        f"Expected exactly one CheckConstraint named ck_llm_providers_kind, "
        f"found {[c.name for c in check_constraints]}"
    )
    sql_text = str(named[0].sqltext)
    for kind in ("zhipu", "openai_compat", "minimax"):
        assert kind in sql_text, (
            f"Kind '{kind}' not mentioned in CheckConstraint SQL: {sql_text}"
        )
