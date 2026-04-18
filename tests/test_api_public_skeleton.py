"""Tests for public API route skeleton."""
from app.main import app


def test_public_router_registered():
    """Test that public routes are registered under /v1."""
    route_paths = [route.path for route in app.routes]
    assert "/v1/config" in route_paths
