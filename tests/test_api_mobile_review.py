"""Tests for mobile review API."""
from app.main import app


def test_review_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/review/today" in paths
    assert "/api/mobile/v1/review/cards" in paths
    assert "/api/mobile/v1/review/progress/{flashcard_id}" in paths
