"""Integration tests for /api/v1/llm/* (Phase D admin API).

Real DB (Phase B seed is assumed), admin-dep overridden so we don't need
to mint a real EdDSA JWT. Each test cleans up its own synthetic rows
(prefix-based) so parallel/repeat runs are safe.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text
from sqlalchemy.exc import OperationalError

from app.api.v1.dependencies import get_current_user
from app.core.database import SessionLocal, get_db
from app.llm import router as task_router
from app.llm.registry import _registry
from app.main import app
from app.models.current_user import CurrentUser
from app.providers.base import ModelInfo


# Marker so the test can clean up only its own rows.
_TEST_USER_ID = "llm_api_e2e_user"
_NAME_PREFIX = "__llm_e2e_"


@pytest.fixture
def real_db(db_engine):
    from app.models import Base

    Base.metadata.create_all(db_engine)

    try:
        db = SessionLocal()
        db.execute(sql_text("SELECT 1"))
    except OperationalError:
        pytest.skip("PostgreSQL test DB not available")

    def _wipe(s):
        # Clean up anything created by this test suite. The seeded Zhipu
        # provider is preserved.
        s.execute(
            sql_text(
                "DELETE FROM llm_provider_models "
                "WHERE provider_id IN (SELECT id FROM llm_providers "
                "WHERE name LIKE :p)"
            ),
            {"p": f"{_NAME_PREFIX}%"},
        )
        s.execute(
            sql_text("DELETE FROM llm_providers WHERE name LIKE :p"),
            {"p": f"{_NAME_PREFIX}%"},
        )
        s.execute(
            sql_text("DELETE FROM audit_logs WHERE user_id = :u"),
            {"u": _TEST_USER_ID},
        )
        s.commit()

    _wipe(db)
    try:
        yield db
    finally:
        _wipe(db)
        db.close()


@pytest.fixture
def admin_user():
    return CurrentUser(
        id=_TEST_USER_ID,
        email="llm-e2e@test",
        role="admin",
    )


@pytest.fixture
def client(real_db, admin_user):
    """TestClient with admin auth overridden (so no JWT mint needed).

    The non-overridden GET paths still exercise the require-auth path —
    see :func:`test_list_providers_has_admin_gating`.
    """
    def override_get_db():
        yield real_db

    def override_current_user():
        return admin_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fresh_router_caches():
    """Isolate test routing caches so PUT-invalidation observations hold."""
    task_router.invalidate_all()
    _registry.invalidate_all()
    yield
    task_router.invalidate_all()
    _registry.invalidate_all()


# ---------------------------------------------------------------------------
# Read-side smoke
# ---------------------------------------------------------------------------


def test_list_providers_returns_seeded_zhipu(client, real_db):
    """The Phase B seed row for Zhipu must be visible."""
    resp = client.get("/api/v1/llm/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = {p["name"] for p in data}
    assert any(n for n in names if "智谱" in n), f"seeded Zhipu missing: {names}"

    # Zero-leak shape check: no response row may carry api_key / api_key_env /
    # extra_headers under ANY key.
    for p in data:
        for forbidden in ("api_key", "api_key_env", "extra_headers"):
            assert forbidden not in p, f"response leaks {forbidden}: {p}"


def test_list_providers_has_admin_gating():
    """Hitting the endpoint with no token (no dep override) must 401."""
    # A TestClient WITHOUT the dep override — directly use app.
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/v1/llm/providers")
    assert resp.status_code == 401, (
        f"llm admin API leaked to anonymous: {resp.status_code}"
    )


def test_get_tasks_returns_seven_routes(client):
    """All 7 task routes should be present (Phase B seed)."""
    resp = client.get("/api/v1/llm/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7, f"expected 7 task routes, got {len(data)}: {data}"

    keys = {r["task_key"] for r in data}
    expected = {
        "qa_generation",
        "qa_facet_extraction",
        "ingest_tagger",
        "ingest_context_enricher",
        "ingest_bridge_linker",
        "content_generation",
        "translation",
    }
    assert keys == expected

    # Every entry must carry its description (from app.core.llm_tasks).
    for r in data:
        assert r["description"], f"missing description: {r}"
        assert r["provider_name"]


# ---------------------------------------------------------------------------
# Delete — in-use enforcement
# ---------------------------------------------------------------------------


def test_delete_provider_in_use_returns_409(client, real_db):
    """Deleting the seeded Zhipu must fail with 409 + task_keys enumeration."""
    # Get the seeded Zhipu's id.
    row = real_db.execute(
        sql_text("SELECT id FROM llm_providers WHERE kind = 'zhipu' LIMIT 1")
    ).first()
    assert row is not None, "Phase B Zhipu seed missing"
    zhipu_id = row[0]

    resp = client.delete(f"/api/v1/llm/providers/{zhipu_id}")
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "provider_in_use"
    assert "task_keys" in detail
    assert len(detail["task_keys"]) == 7, detail["task_keys"]


# ---------------------------------------------------------------------------
# Create → read flow
# ---------------------------------------------------------------------------


def test_create_provider_then_get_returns_public_shape(
    client, real_db, monkeypatch
):
    """POST then GET — verify has_api_key_configured and public shape."""
    env_name = "LLM_E2E_TEST_KEY"
    monkeypatch.setenv(env_name, "very-secret-value-with-enough-length")

    payload = {
        "name": f"{_NAME_PREFIX}openai",
        "kind": "openai_compat",
        "base_url": "https://api.e2e.example.com/v1",
        "api_key_env": env_name,
        "extra_headers": {"X-Tenant": "t1"},
        "enabled": True,
        "timeout_read": 60.0,
    }
    resp = client.post("/api/v1/llm/providers", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()

    # Zero-leak: secrets must not round-trip in the response.
    for forbidden in ("api_key", "api_key_env", "extra_headers"):
        assert forbidden not in created, f"response leaks {forbidden}"
    assert created["has_api_key_configured"] is True
    assert created["model_count"] == 0

    provider_id = created["id"]

    resp2 = client.get(f"/api/v1/llm/providers/{provider_id}")
    assert resp2.status_code == 200
    fetched = resp2.json()
    assert fetched["id"] == provider_id
    assert fetched["name"] == payload["name"]
    assert fetched["has_api_key_configured"] is True
    assert "api_key_env" not in fetched


def test_create_provider_unset_env_reports_not_configured(client, real_db):
    """When api_key_env is unset in the process, has_api_key_configured=False."""
    # Ensure the env var is unset (monkeypatch with delenv in case of bleed).
    # Use a unique name the process will never have set.
    unset_env = "LLM_E2E_DEFINITELY_NOT_SET"
    os.environ.pop(unset_env, None)

    payload = {
        "name": f"{_NAME_PREFIX}unset",
        "kind": "openai_compat",
        "base_url": "https://api.unset.example.com/v1",
        "api_key_env": unset_env,
    }
    resp = client.post("/api/v1/llm/providers", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["has_api_key_configured"] is False


# ---------------------------------------------------------------------------
# PUT /tasks/{key} invalidates router cache
# ---------------------------------------------------------------------------


def test_put_task_route_invalidates_cache(client, real_db, monkeypatch):
    """After PUT /tasks/{key}, next get_for_task sees the new provider/model."""
    # Grab the seeded Zhipu provider id.
    row = real_db.execute(
        sql_text("SELECT id FROM llm_providers WHERE kind = 'zhipu' LIMIT 1")
    ).first()
    assert row is not None
    zhipu_id = str(row[0])

    # Warm the cache for qa_generation.
    from app.llm import router as routermod

    provider, model = routermod.get_for_task("qa_generation")
    original_model = model  # seeded value (glm-4.7)

    # PUT to a new model_id. Provider stays the same.
    new_model = "glm-4.7-warmcache-test"
    payload = {
        "task_key": "qa_generation",
        "provider_id": zhipu_id,
        "model_id": new_model,
    }
    resp = client.put("/api/v1/llm/tasks/qa_generation", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model_id"] == new_model
    assert body["task_key"] == "qa_generation"

    # Next get_for_task call should see the new model (cache was invalidated).
    _, refreshed_model = routermod.get_for_task("qa_generation")
    assert refreshed_model == new_model, (
        f"cache not invalidated: got {refreshed_model!r}, expected {new_model!r}"
    )

    # Restore the original for idempotence.
    restore = {
        "task_key": "qa_generation",
        "provider_id": zhipu_id,
        "model_id": original_model,
    }
    resp = client.put("/api/v1/llm/tasks/qa_generation", json=restore)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /providers/{id}/test — success + failure paths
# ---------------------------------------------------------------------------


def test_provider_test_success_refreshes_model_cache(client, real_db):
    """Happy path: stub list_models(), verify llm_provider_models got repopulated."""
    row = real_db.execute(
        sql_text("SELECT id FROM llm_providers WHERE kind = 'zhipu' LIMIT 1")
    ).first()
    zhipu_id = row[0]

    fake_models = [
        ModelInfo(id="fake-model-a", display_name="Fake A", kind="chat"),
        ModelInfo(id="fake-model-b", display_name="Fake B", kind="chat"),
    ]

    with patch(
        "app.providers.zhipu.ZhipuProvider.list_models",
        new=AsyncMock(return_value=fake_models),
    ):
        resp = client.post(f"/api/v1/llm/providers/{zhipu_id}/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_count"] == 2

    # DB should now have the two models cached.
    cached = real_db.execute(
        sql_text(
            "SELECT model_id FROM llm_provider_models "
            "WHERE provider_id = :pid ORDER BY model_id"
        ),
        {"pid": zhipu_id},
    ).fetchall()
    assert [r[0] for r in cached] == ["fake-model-a", "fake-model-b"]


def test_provider_test_failure_records_reason(client, real_db):
    """list_models() raising → status=fail + sanitized reason + row updated."""
    row = real_db.execute(
        sql_text("SELECT id FROM llm_providers WHERE kind = 'zhipu' LIMIT 1")
    ).first()
    zhipu_id = row[0]

    from app.providers.errors import ProviderUnavailableError

    with patch(
        "app.providers.zhipu.ZhipuProvider.list_models",
        new=AsyncMock(
            side_effect=ProviderUnavailableError("upstream 503 simulated")
        ),
    ):
        resp = client.post(f"/api/v1/llm/providers/{zhipu_id}/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "fail"
    assert "simulated" in (body["reason"] or "") or "503" in (body["reason"] or "")
