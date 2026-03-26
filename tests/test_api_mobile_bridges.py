"""Tests for mobile bridges API endpoints."""
from app.main import app


def test_mobile_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges" in route_paths


def test_mobile_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}" in route_paths


def test_mobile_bridges_knowledge_points_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}/knowledge-points" in route_paths
