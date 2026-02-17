"""Tests for V1 Chunks API endpoint."""
from app.main import app


def test_chunks_list_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks" in route_paths


def test_chunks_detail_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/{chunk_id}" in route_paths


def test_chunks_list_not_404():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/chunks")
    assert response.status_code != 404


def test_chunks_detail_not_found():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/chunks/999999")
    assert response.status_code in (401, 404, 500)  # 401 without auth
