"""Tests for mobile search endpoint (placeholder)."""
from app.main import app


def test_mobile_search_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/search" in route_paths
