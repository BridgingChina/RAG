"""Tests for mobile knowledge API endpoints."""
from app.main import app


def test_mobile_knowledge_tree_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/tree" in route_paths


def test_mobile_knowledge_point_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/points/{point_id}" in route_paths


def test_mobile_knowledge_point_bridges_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/points/{point_id}/bridges" in route_paths


def test_knowledge_point_flashcards_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/knowledge/points/{point_id}/flashcards" in route_paths
