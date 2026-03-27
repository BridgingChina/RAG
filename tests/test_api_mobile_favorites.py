"""Tests for mobile favorites API."""
from app.main import app


def test_favorites_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/favorites" in paths
    assert "/api/mobile/v1/favorites/{favorite_id}" in paths
    assert "/api/mobile/v1/favorites/check" in paths
