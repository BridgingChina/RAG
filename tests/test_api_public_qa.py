"""Tests for public QA SSE endpoint."""
from app.main import app


def test_public_qa_ask_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/v1/qa/ask" in route_paths


def test_public_qa_ask_accepts_post():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/qa/ask",
        json={"question": "测试问题"},
    )
    assert response.status_code not in (404, 405)


def test_qa_request_rejects_empty_question():
    """POST with empty question string returns 422."""
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/qa/ask",
        json={"question": ""},
    )
    assert response.status_code == 422


def test_qa_context_rejects_invalid_type():
    """POST with invalid context type returns 422."""
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/qa/ask",
        json={"question": "test", "context": {"type": "invalid_type"}},
    )
    assert response.status_code == 422
