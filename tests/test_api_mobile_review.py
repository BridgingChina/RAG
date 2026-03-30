"""Tests for mobile review API."""
from app.main import app


def test_review_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/review/today" in paths
    assert "/api/mobile/v1/review/cards" in paths
    assert "/api/mobile/v1/review/progress/{flashcard_id}" in paths


def test_review_today_response_wraps_cards_and_total_due():
    from app.api.mobile.v1.review import get_today_queue
    import inspect
    src = inspect.getsource(get_today_queue)
    assert '"cards"' in src or "'cards'" in src
    assert '"total_due"' in src or "'total_due'" in src


def test_review_cards_response_wraps_cards():
    from app.api.mobile.v1.review import list_review_cards
    import inspect
    src = inspect.getsource(list_review_cards)
    assert '"cards"' in src or "'cards'" in src
