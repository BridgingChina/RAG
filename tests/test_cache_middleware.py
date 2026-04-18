"""Tests for PublicCacheMiddleware."""

import pytest

from app.core.cache_middleware import (
    CACHE_MAX_AGE,
    PUBLIC_PREFIX,
    PublicCacheMiddleware,
    _NO_CACHE_PREFIXES,
)


def test_constants():
    """Verify middleware constants are set correctly."""
    assert CACHE_MAX_AGE == 300
    assert PUBLIC_PREFIX == "/v1/"
    assert "/v1/favorites" in _NO_CACHE_PREFIXES
    assert "/v1/review" in _NO_CACHE_PREFIXES
    assert "/v1/history" in _NO_CACHE_PREFIXES


def test_middleware_class_exists():
    """PublicCacheMiddleware is importable and is a middleware."""
    from starlette.middleware.base import BaseHTTPMiddleware

    assert issubclass(PublicCacheMiddleware, BaseHTTPMiddleware)


@pytest.fixture
def app_with_middleware():
    """Create a minimal Starlette app with the cache middleware for testing."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def public_bridges(request):
        return JSONResponse({"data": []})

    async def public_favorites(request):
        return JSONResponse({"data": []})

    async def public_review(request):
        return JSONResponse({"data": []})

    async def public_history(request):
        return JSONResponse({"data": []})

    async def public_config(request):
        return JSONResponse({"data": {}})

    async def admin_endpoint(request):
        return JSONResponse({"items": []})

    routes = [
        Route("/v1/bridges", public_bridges),
        Route("/v1/config", public_config),
        Route("/v1/favorites", public_favorites),
        Route("/v1/review/today", public_review),
        Route("/v1/history", public_history),
        Route("/api/v1/bridges", admin_endpoint),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(PublicCacheMiddleware)
    return app


@pytest.fixture
def client(app_with_middleware):
    from starlette.testclient import TestClient

    return TestClient(app_with_middleware)


class TestPublicCacheHeaders:
    """Test Cache-Control headers on public endpoints."""

    def test_public_bridges_get_has_cache_header(self, client):
        resp = client.get("/v1/bridges")
        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "public, max-age=300"

    def test_public_config_get_has_cache_header(self, client):
        resp = client.get("/v1/config")
        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "public, max-age=300"

    def test_public_favorites_no_cache_header(self, client):
        resp = client.get("/v1/favorites")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_public_review_no_cache_header(self, client):
        resp = client.get("/v1/review/today")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_public_history_no_cache_header(self, client):
        resp = client.get("/v1/history")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_admin_endpoint_no_cache_header(self, client):
        resp = client.get("/api/v1/bridges")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_post_request_no_cache_header(self, client):
        """POST requests should never get cache headers."""
        resp = client.post("/v1/bridges")
        # 405 is expected since route only handles GET
        assert "Cache-Control" not in resp.headers
