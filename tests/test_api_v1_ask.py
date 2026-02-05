"""Tests for V1 Ask API endpoint."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_v1_endpoint_exists():
    """Test that /api/v1/ask endpoint is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/ask" in route_paths


def test_ask_v1_endpoint_schema(client):
    """Test request validation for /api/v1/ask."""
    response = client.post("/api/v1/ask", json={})
    assert response.status_code == 422  # Missing required field 'question'


