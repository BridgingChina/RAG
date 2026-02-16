"""Tests for V1 System API endpoint."""
from app.main import app


def test_system_status_endpoint_exists():
    """Test that /api/v1/system/status is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/system/status" in route_paths


def test_system_status_response_not_404():
    """Test system status returns a response (may fail on DB, but not 404)."""
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/system/status")
    assert response.status_code != 404
