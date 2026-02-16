"""Tests for V1 Taxonomy API endpoint."""
from app.main import app


def test_taxonomy_tree_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/taxonomy/tree" in route_paths


def test_taxonomy_nodes_create_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/taxonomy/nodes" in route_paths


def test_taxonomy_batch_update_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/taxonomy/batch-update" in route_paths
