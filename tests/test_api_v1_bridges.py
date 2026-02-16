"""Tests for V1 Bridges API endpoint."""
from app.main import app


def test_bridges_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges" in route_paths


def test_bridges_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges/{bridge_id}" in route_paths


def test_bridges_create_accepts_post():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/bridges", json={"name": "测试桥"})
    assert response.status_code not in (404, 405)


def test_bridges_chunks_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges/{bridge_id}/chunks" in route_paths


def test_bridges_merge_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/bridges/{target_id}/merge" in route_paths
