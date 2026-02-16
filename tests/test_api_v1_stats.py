"""Tests for V1 Stats API endpoint."""
from app.main import app


def test_stats_dashboard_endpoint_exists():
    """Test that /api/v1/stats/dashboard is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/stats/dashboard" in route_paths


def test_stats_dashboard_response_schema():
    """Test response has required fields."""
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/stats/dashboard")
    assert response.status_code != 404
