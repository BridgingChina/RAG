"""Admin translations API smoke tests (i18n Phase 3).

Focuses on route registration + input validation — end-to-end审校 behaviour is
covered by the service-layer tests in ``test_translation_service.py``.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_admin_translation_routes_registered():
    """All five endpoints must be registered under /api/v1/translations."""
    paths = {r.path for r in app.routes}
    expected = {
        "/api/v1/translations",
        "/api/v1/translations/generate",
        "/api/v1/translations/batch-generate",
        "/api/v1/translations/{review_id}/review",
        "/api/v1/translations/coverage",
    }
    assert expected.issubset(paths), f"Missing routes: {expected - paths}"


def test_admin_translation_endpoints_require_auth():
    """Unauthenticated requests must be rejected with 401 (not 200)."""
    client = TestClient(app)
    # GET list
    assert client.get("/api/v1/translations").status_code in {401, 403}
    # GET coverage
    assert client.get("/api/v1/translations/coverage").status_code in {401, 403}
    # POST generate
    assert client.post(
        "/api/v1/translations/generate",
        json={
            "table_name": "bridges",
            "row_id": "00000000-0000-0000-0000-000000000000",
            "field_name": "name_en",
        },
    ).status_code in {401, 403}
