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
    response = client.get("/api/v1/chunks/00000000-0000-0000-0000-999999999999")
    assert response.status_code in (401, 404)  # 401 without auth


def test_chunks_split_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/{chunk_id}/split" in route_paths


def test_chunks_merge_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/merge" in route_paths


def test_chunks_batch_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/chunks/batch" in route_paths


def test_sources_reindex_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/sources/{source_id}/reindex" in route_paths
