"""Phase 2 end-to-end wiring smoke tests.

Exercises the full auth surface shape with TestClient: routes register in
the right groups, unauthenticated requests get the right status codes, and
protected endpoints actually enforce ``require_user`` / ``get_current_user``.

True round-trip E2E against a live ``auth.bridgingchina.net`` Worker is
out of scope — those checks belong to the deploy window (Task 2.F.5) and
require real JWKS access.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_phase2_routes_registered():
    paths = {r.path for r in app.routes}

    # Admin surface: /me is the only /auth/* route.
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/auth/login" not in paths
    assert "/api/v1/auth/password" not in paths

    # Public user-scoped routes.
    assert "/v1/favorites" in paths
    assert "/v1/history" in paths
    assert "/v1/review/today" in paths

    # Internal Worker-webhook surface.
    assert "/internal/users/{user_id}/purge" in paths


def test_admin_endpoint_without_jwt_is_401():
    client = TestClient(app, raise_server_exceptions=False)
    for path in [
        "/api/v1/auth/me",
        "/api/v1/chunks",
        "/api/v1/bridges",
        "/api/v1/sources",
        "/api/v1/audit-logs",
    ]:
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} leaked to anonymous"


def test_admin_endpoint_rejects_malformed_bearer():
    """A syntactically-invalid Bearer (not a real JWT) must 401, not 500."""
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert resp.status_code == 401


def test_public_per_user_endpoints_require_jwt():
    """Favorites / history / review flip from anonymous to 401 without a JWT."""
    client = TestClient(app, raise_server_exceptions=False)
    for path in ["/v1/favorites", "/v1/history", "/v1/review/today"]:
        resp = client.get(path)
        assert resp.status_code == 401, f"{path} should require JWT"


def test_public_anonymous_reads_still_work():
    """Bridges / knowledge tree must stay reachable without any token.

    We only check the auth layer (no 401) — the endpoints may still return
    200 or a DB-dependent status depending on the test DB state.
    """
    client = TestClient(app, raise_server_exceptions=False)
    for path in ["/v1/config", "/v1/knowledge/tree"]:
        resp = client.get(path)
        assert resp.status_code != 401, f"{path} must not require auth"


def test_health_is_public():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200


def test_cors_origins_include_three_phase2_domains():
    """Phase 2 production domains must be allowed by CORS default config."""
    from app.core.config import settings
    for origin in (
        "https://auth.bridgingchina.net",
        "https://console.bridgingchina.net",
        "https://bridgingchina.net",
    ):
        assert origin in settings.cors_origins, f"{origin} missing from CORS default"
