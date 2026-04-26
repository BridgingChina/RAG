"""Global error handlers for public API endpoints.

Converts FastAPI's default {"detail": "..."} error format to the public spec
format: {"error": {"code": "NOT_FOUND", "message": "..."}}.

Only affects requests under /v1/ — admin API responses are unchanged.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

_STATUS_TO_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "UNPROCESSABLE",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def register_public_error_handlers(app: FastAPI) -> None:
    """Register error handlers that convert HTTP errors to public spec format."""

    @app.exception_handler(HTTPException)
    async def _public_http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        # Only convert for public API routes (/v1/*)
        if not request.url.path.startswith("/v1/"):
            # Preserve FastAPI default format for admin / non-/v1 routes
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=getattr(exc, "headers", None),
            )

        # Structured detail: routes can opt into custom code+message by raising
        # HTTPException(status, detail={"code": "...", "message": "..."}).
        # Falls back to the legacy string-or-status-code shape otherwise.
        if (
            isinstance(exc.detail, dict)
            and isinstance(exc.detail.get("code"), str)
            and isinstance(exc.detail.get("message"), str)
        ):
            code = exc.detail["code"]
            message = exc.detail["message"]
        else:
            code = _STATUS_TO_CODE.get(exc.status_code, f"HTTP_{exc.status_code}")
            message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message}},
            headers=getattr(exc, "headers", None),
        )
