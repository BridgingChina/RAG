"""Tests for mobile API route skeleton."""
from app.main import app


def test_mobile_router_registered():
    """Test that mobile routes are registered under /api/mobile/v1."""
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/config" in route_paths
