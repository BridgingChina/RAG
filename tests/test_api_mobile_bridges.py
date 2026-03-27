"""Tests for mobile bridges API endpoints."""
from app.main import app


def test_mobile_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges" in route_paths


def test_mobile_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}" in route_paths


def test_mobile_bridges_clusters_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/clusters" in route_paths


def test_mobile_bridges_knowledge_points_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/bridges/{bridge_id}/knowledge-points" in route_paths


def test_lvl1_to_section_mapping():
    from app.api.mobile.v1.bridges import LVL1_TO_SECTION
    assert LVL1_TO_SECTION["形制与技术"] == "structure"
    assert LVL1_TO_SECTION["地域与环境"] == "geography"
    assert LVL1_TO_SECTION["功能与社会"] == "society"
    assert LVL1_TO_SECTION["历史与演变"] == "history"
