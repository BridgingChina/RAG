"""Tests for public review API."""
from app.main import app


def test_review_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/v1/review/today" in paths
    assert "/v1/review/cards" in paths
    assert "/v1/review/progress/{flashcard_id}" in paths


def test_review_today_response_wraps_cards_and_total_due():
    from app.api.public.v1.review import get_today_queue
    import inspect
    src = inspect.getsource(get_today_queue)
    assert '"cards"' in src or "'cards'" in src
    assert '"total_due"' in src or "'total_due'" in src


def test_review_today_has_pagination_params():
    from app.api.public.v1.review import get_today_queue
    import inspect
    sig = inspect.signature(get_today_queue)
    assert "page" in sig.parameters
    assert "page_size" in sig.parameters


def test_review_cards_response_wraps_cards():
    from app.api.public.v1.review import list_review_cards
    import inspect
    src = inspect.getsource(list_review_cards)
    assert '"cards"' in src or "'cards'" in src


def test_format_card_uses_id_not_flashcard_id():
    from app.api.public.v1.review import _format_card
    import inspect
    src = inspect.getsource(_format_card)
    assert '"id"' in src
    assert '"flashcard_id"' not in src


def test_format_card_uses_example_bridge_object():
    from app.api.public.v1.review import _format_card
    import inspect
    src = inspect.getsource(_format_card)
    assert '"example_bridge"' in src or "'example_bridge'" in src
    assert '"example_bridge_id"' not in src and "'example_bridge_id'" not in src


def test_update_progress_uses_reviewed_at():
    from app.api.public.v1.review import update_review_progress
    import inspect
    src = inspect.getsource(update_review_progress)
    assert '"reviewed_at"' in src or "'reviewed_at'" in src
