"""Tests for V1 Sources API endpoint."""
from app.main import app


def test_sources_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/sources" in route_paths


def test_sources_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/sources/{source_id}" in route_paths
