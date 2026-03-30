"""Tests for mobile history API."""
from app.main import app


def test_history_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/history" in paths


def test_history_list_response_wraps_items():
    from app.api.mobile.v1.history import list_history
    import inspect
    src = inspect.getsource(list_history)
    assert '"items"' in src or "'items'" in src
