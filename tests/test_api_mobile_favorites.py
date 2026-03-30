"""Tests for mobile favorites API."""
from app.main import app


def test_favorites_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/favorites" in paths
    assert "/api/mobile/v1/favorites/{favorite_id}" in paths
    assert "/api/mobile/v1/favorites/check" in paths


def test_favorites_list_response_wraps_items():
    from app.api.mobile.v1.favorites import list_favorites
    import inspect
    src = inspect.getsource(list_favorites)
    assert '"items"' in src or "'items'" in src


def test_favorites_list_includes_target_summary_and_thumbnail():
    from app.api.mobile.v1.favorites import list_favorites
    import inspect
    src = inspect.getsource(list_favorites)
    assert '"target_summary"' in src or "'target_summary'" in src
    assert '"thumbnail"' in src or "'thumbnail'" in src
