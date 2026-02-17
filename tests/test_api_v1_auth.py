"""Tests for V1 Auth API endpoints."""

from app.main import app


def test_auth_login_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/login" in route_paths


def test_auth_me_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/me" in route_paths


def test_auth_password_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/password" in route_paths


def test_login_rejects_missing_credentials():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422


def test_me_rejects_unauthenticated():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_protected_routes_reject_unauthenticated():
    """All non-auth API routes should require authentication."""
    from fastapi.testclient import TestClient

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
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
