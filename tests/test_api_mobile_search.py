"""Tests for mobile unified search."""
from app.main import app
from app.api.mobile.v1.search import _highlight, _escape_like


def test_highlight_wraps_keyword():
    assert "<em>拱桥</em>" in _highlight("石拱桥结构", "拱桥")


def test_highlight_case_insensitive():
    assert "<em>Bridge</em>" in _highlight("Old Bridge", "bridge")


def test_highlight_no_match_returns_original():
    assert _highlight("赵州桥", "卢沟桥") == "赵州桥"


def test_escape_like():
    assert _escape_like("100%") == "100\\%"
    assert _escape_like("a_b") == "a\\_b"


def test_search_route_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/search" in route_paths
