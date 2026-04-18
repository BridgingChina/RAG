"""Cache-Control middleware for public read-only endpoints."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Public path prefixes that require X-Device-Id (per-device state, not cacheable)
_NO_CACHE_PREFIXES = (
    "/v1/favorites",
    "/v1/review",
    "/v1/history",
)

PUBLIC_PREFIX = "/v1/"
CACHE_MAX_AGE = 300  # 5 minutes


class PublicCacheMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control headers to public read-only GET endpoints.

    Excludes device-specific endpoints (favorites, review, history)
    that depend on X-Device-Id and should not be cached.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if (
            request.method == "GET"
            and request.url.path.startswith(PUBLIC_PREFIX)
            and not any(request.url.path.startswith(p) for p in _NO_CACHE_PREFIXES)
        ):
            response.headers["Cache-Control"] = f"public, max-age={CACHE_MAX_AGE}"

        return response
