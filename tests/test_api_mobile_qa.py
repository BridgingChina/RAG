"""Tests for mobile QA SSE endpoint."""
from app.main import app


def test_mobile_qa_ask_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/mobile/v1/qa/ask" in route_paths


def test_mobile_qa_ask_accepts_post():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/mobile/v1/qa/ask",
        json={"question": "测试问题"},
    )
    assert response.status_code not in (404, 405)
