"""Smoke tests for /internal/users/{user_id}/purge."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_purge_route_exists():
    paths = [r.path for r in app.routes]
    assert "/internal/users/{user_id}/purge" in paths


def test_purge_rejects_missing_token_as_forbidden_when_configured():
    """With a secret configured but no header, expect 403."""
    with patch("app.api.internal.purge.settings") as mock_settings:
        mock_settings.internal_api_secret = "s3cret"
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/internal/users/abc/purge")
        assert resp.status_code == 403


def test_purge_returns_503_when_secret_unconfigured():
    """Secret absent → endpoint refuses every request with 503."""
    with patch("app.api.internal.purge.settings") as mock_settings:
        mock_settings.internal_api_secret = ""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/internal/users/abc/purge", headers={"X-Internal-Token": "anything"})
        assert resp.status_code == 503


def test_purge_rejects_wrong_token():
    with patch("app.api.internal.purge.settings") as mock_settings:
        mock_settings.internal_api_secret = "right"
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/internal/users/abc/purge",
            headers={"X-Internal-Token": "wrong"},
        )
        assert resp.status_code == 403
