"""Tests for MobileCacheMiddleware."""

import pytest

from app.core.cache_middleware import (
    CACHE_MAX_AGE,
    MOBILE_PREFIX,
    MobileCacheMiddleware,
    _NO_CACHE_PREFIXES,
)


def test_constants():
    """Verify middleware constants are set correctly."""
    assert CACHE_MAX_AGE == 300
    assert MOBILE_PREFIX == "/api/mobile/v1/"
    assert "/api/mobile/v1/favorites" in _NO_CACHE_PREFIXES
    assert "/api/mobile/v1/review" in _NO_CACHE_PREFIXES
    assert "/api/mobile/v1/history" in _NO_CACHE_PREFIXES


def test_middleware_class_exists():
    """MobileCacheMiddleware is importable and is a middleware."""
    from starlette.middleware.base import BaseHTTPMiddleware

    assert issubclass(MobileCacheMiddleware, BaseHTTPMiddleware)


@pytest.fixture
def app_with_middleware():
    """Create a minimal Starlette app with the cache middleware for testing."""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def mobile_bridges(request):
        return JSONResponse({"data": []})

    async def mobile_favorites(request):
        return JSONResponse({"data": []})

    async def mobile_review(request):
        return JSONResponse({"data": []})

    async def mobile_history(request):
        return JSONResponse({"data": []})

    async def mobile_config(request):
        return JSONResponse({"data": {}})

    async def admin_endpoint(request):
        return JSONResponse({"items": []})

    routes = [
        Route("/api/mobile/v1/bridges", mobile_bridges),
        Route("/api/mobile/v1/config", mobile_config),
        Route("/api/mobile/v1/favorites", mobile_favorites),
        Route("/api/mobile/v1/review/today", mobile_review),
        Route("/api/mobile/v1/history", mobile_history),
        Route("/api/v1/bridges", admin_endpoint),
    ]

    app = Starlette(routes=routes)
    app.add_middleware(MobileCacheMiddleware)
    return app


@pytest.fixture
def client(app_with_middleware):
    from starlette.testclient import TestClient

    return TestClient(app_with_middleware)


class TestMobileCacheHeaders:
    """Test Cache-Control headers on mobile endpoints."""

    def test_mobile_bridges_get_has_cache_header(self, client):
        resp = client.get("/api/mobile/v1/bridges")
        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "public, max-age=300"

    def test_mobile_config_get_has_cache_header(self, client):
        resp = client.get("/api/mobile/v1/config")
        assert resp.status_code == 200
        assert resp.headers["Cache-Control"] == "public, max-age=300"

    def test_mobile_favorites_no_cache_header(self, client):
        resp = client.get("/api/mobile/v1/favorites")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_mobile_review_no_cache_header(self, client):
        resp = client.get("/api/mobile/v1/review/today")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_mobile_history_no_cache_header(self, client):
        resp = client.get("/api/mobile/v1/history")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_admin_endpoint_no_cache_header(self, client):
        resp = client.get("/api/v1/bridges")
        assert resp.status_code == 200
        assert "Cache-Control" not in resp.headers

    def test_post_request_no_cache_header(self, client):
        """POST requests should never get cache headers."""
        resp = client.post("/api/mobile/v1/bridges")
        # 405 is expected since route only handles GET
        assert "Cache-Control" not in resp.headers
