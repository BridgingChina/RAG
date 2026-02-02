import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_endpoint_schema(client):
    # Test request validation
    response = client.post("/ask", json={})
    assert response.status_code == 422  # Missing required field


@patch("app.api.ask.Retriever")
@patch("app.api.ask.Generator")
@patch("app.api.ask.ZhipuProvider")
def test_ask_endpoint_success(mock_provider, mock_generator, mock_retriever, client):
    # Setup mocks
    mock_retriever_instance = AsyncMock()
    mock_retriever_instance.retrieve.return_value = []
    mock_retriever.return_value = mock_retriever_instance

    mock_generator_instance = AsyncMock()
    mock_generator_instance.generate = AsyncMock(
        return_value=AsyncMock(
            summary="测试摘要",
            details="测试详情",
            citations=[],
            sources=[],
        )
    )
    mock_generator.return_value = mock_generator_instance

    response = client.post("/ask", json={"question": "什么是赵州桥？"})

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "details" in data
    assert "citations" in data
