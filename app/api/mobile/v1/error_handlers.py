"""Global error handlers for mobile API endpoints.

Converts FastAPI's default {"detail": "..."} error format to the mobile spec
format: {"error": {"code": "NOT_FOUND", "message": "..."}}.

Only affects requests under /api/mobile/ — admin API responses are unchanged.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

_STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "UNPROCESSABLE",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def register_mobile_error_handlers(app: FastAPI) -> None:
    """Register error handlers that convert HTTP errors to mobile spec format."""

    @app.exception_handler(HTTPException)
    async def _mobile_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        # Only convert for mobile API routes
        if not request.url.path.startswith("/api/mobile/"):
            # Preserve FastAPI default format for non-mobile routes
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )

        code = _STATUS_TO_CODE.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message}},
            headers=getattr(exc, "headers", None),
        )
