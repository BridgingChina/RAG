"""Tests for V1 Auth API endpoints.

Phase 2: login/logout/password no longer exist on FastAPI — those flows
moved to auth.bridgingchina.net. The only admin auth surface here is
``GET /api/v1/auth/me`` which requires a verified JWT and projects the
payload into ``UserInfo``.
"""
from fastapi.testclient import TestClient

from app.main import app


def test_auth_me_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/me" in route_paths


def test_legacy_login_endpoint_removed():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/login" not in route_paths
    assert "/api/v1/auth/password" not in route_paths


def test_me_rejects_unauthenticated():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_protected_routes_reject_unauthenticated():
    """All non-auth API routes should require authentication."""
    client = TestClient(app, raise_server_exceptions=False)

    protected_gets = [
        "/api/v1/chunks",
        "/api/v1/bridges",
        "/api/v1/sources",
        "/api/v1/stats/dashboard",
    ]
    for path in protected_gets:
        response = client.get(path)
        assert response.status_code == 401, f"{path} should be protected"


def test_health_remains_public():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
