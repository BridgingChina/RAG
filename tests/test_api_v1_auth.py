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


def test_login_rate_limit_returns_429():
    """After rate limit is hit, login endpoint returns 429 before touching DB."""
    from fastapi.testclient import TestClient
    from app.api.v1 import auth as auth_module

    client = TestClient(app, raise_server_exceptions=False)

    # Simulate 5 prior failures by directly populating the tracker
    ip = "testclient"
    with auth_module._lock:
        auth_module._failed_attempts.clear()
    for _ in range(5):
        auth_module._record_failure(ip)

    # Next attempt should be rate-limited (429) — no DB needed
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "anyone", "password": "anything"},
    )
    assert resp.status_code == 429
    assert "Too many" in resp.json()["detail"]

    # Cleanup
    with auth_module._lock:
        auth_module._failed_attempts.clear()


def test_login_rate_limit_reset_helpers():
    """Unit test for the rate limiter helper functions."""
    from app.api.v1.auth import _record_failure, _reset, _cleanup_and_check, _failed_attempts, _lock

    # Clean state
    with _lock:
        _failed_attempts.clear()

    ip = "192.0.2.99"

    # Should not be locked initially
    assert _cleanup_and_check(ip) is False

    # Record 4 failures — still not locked
    for _ in range(4):
        _record_failure(ip)
    assert _cleanup_and_check(ip) is False

    # 5th failure triggers lockout
    _record_failure(ip)
    assert _cleanup_and_check(ip) is True

    # Reset clears lockout
    _reset(ip)
    assert _cleanup_and_check(ip) is False

    # Cleanup
    with _lock:
        _failed_attempts.clear()
