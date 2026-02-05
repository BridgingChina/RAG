"""Tests for V1 Ingest API endpoint."""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_ingest_v1_endpoint_exists():
    """Test that /api/v1/ingest endpoint is registered."""
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/ingest" in route_paths


def test_ingest_v1_endpoint_schema(client):
    """Test request validation for /api/v1/ingest."""
    response = client.post("/api/v1/ingest", json={})
    assert response.status_code == 422  # Missing required field 'content'


def test_ingest_request_requires_content(client):
    """Test that content field is required."""
    response = client.post(
        "/api/v1/ingest",
        json={"source_type": "note"},
    )
    assert response.status_code == 422


def test_ingest_response_schema():
    """Test IngestResponse schema structure."""
    from app.api.v1.schemas import IngestResponse, IngestedChunkSummary

    response = IngestResponse(
        source_id=1,
        bridge_name="赵州桥",
        title="测试文档",
        chunk_count=2,
        chunks=[
            IngestedChunkSummary(
                content_preview="测试内容...",
                lvl1="形制与技术",
                lvl2="结构体系",
                bridge_name="赵州桥",
            )
        ],
    )
    assert response.source_id == 1
    assert response.chunk_count == 2
    assert len(response.chunks) == 1
