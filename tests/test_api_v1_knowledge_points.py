"""Tests for admin knowledge points API."""
from app.main import app


def test_knowledge_points_routes_registered():
    paths = [route.path for route in app.routes]
    assert "/api/v1/knowledge-points" in paths
    assert "/api/v1/knowledge-points/{kp_id}" in paths
    assert "/api/v1/knowledge-points/{kp_id}/generate-key-points" in paths
