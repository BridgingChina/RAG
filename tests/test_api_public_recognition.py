"""Route registration tests for /v1/recognition. Full e2e tests in Task 8."""
import io

from fastapi.testclient import TestClient

from app.main import app


def test_recognition_route_registered():
    paths = [r.path for r in app.routes]
    assert "/v1/recognition" in paths


def test_recognition_route_is_post_only():
    """GET /v1/recognition should not be exposed."""
    methods_by_path: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path:
            methods_by_path.setdefault(path, set()).update(methods)
    methods = methods_by_path.get("/v1/recognition", set())
    assert "POST" in methods
    assert "GET" not in methods


def test_recognition_415_returns_structured_error():
    """Wrong MIME → 415 with code='unsupported_media_type'."""
    client = TestClient(app)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("evil.gif", io.BytesIO(b"GIF89a"), "image/gif")},
    )
    assert resp.status_code == 415
    body = resp.json()
    assert body["error"]["code"] == "unsupported_media_type"
    assert "image/jpeg" in body["error"]["message"]


def test_recognition_413_returns_structured_error(monkeypatch):
    """Oversize → 413 with code='file_too_large'."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "recognition_max_image_bytes", 100)

    client = TestClient(app)
    big = io.BytesIO(b"x" * 200)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("big.jpg", big, "image/jpeg")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "file_too_large"


def test_recognition_503_when_api_key_missing(monkeypatch):
    """Missing API key → 503 with code='vision_disabled' (NOT 'SERVICE_UNAVAILABLE')."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "openrouter_api_key", "")

    client = TestClient(app)
    resp = client.post(
        "/v1/recognition",
        files={"image": ("test.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fake"), "image/jpeg")},
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "vision_disabled"
