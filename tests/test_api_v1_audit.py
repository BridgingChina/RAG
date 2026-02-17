"""Tests for V1 Audit Log API endpoint."""

from app.main import app


def test_audit_logs_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/audit-logs" in route_paths


def test_audit_logs_requires_auth():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/audit-logs")
    assert response.status_code == 401
