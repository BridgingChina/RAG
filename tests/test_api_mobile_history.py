"""Tests for mobile history API."""
from app.main import app


def test_history_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/history" in paths
