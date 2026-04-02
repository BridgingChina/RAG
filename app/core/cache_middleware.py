"""Cache-Control middleware for mobile read-only endpoints."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Mobile path prefixes that require X-Device-Id (per-device state, not cacheable)
_NO_CACHE_PREFIXES = (
    "/api/mobile/v1/favorites",
    "/api/mobile/v1/review",
    "/api/mobile/v1/history",
)

MOBILE_PREFIX = "/api/mobile/v1/"
CACHE_MAX_AGE = 300  # 5 minutes


class MobileCacheMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control headers to public mobile GET endpoints.

    Excludes device-specific endpoints (favorites, review, history)
    that depend on X-Device-Id and should not be cached.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if (
            request.method == "GET"
            and request.url.path.startswith(MOBILE_PREFIX)
            and not any(request.url.path.startswith(p) for p in _NO_CACHE_PREFIXES)
        ):
            response.headers["Cache-Control"] = f"public, max-age={CACHE_MAX_AGE}"

        return response
