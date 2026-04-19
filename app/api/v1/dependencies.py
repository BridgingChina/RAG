"""Shared API dependencies for the admin /api/v1 surface.

Phase 2 refactor: ``get_current_user`` now verifies an EdDSA JWT issued by
``auth.bridgingchina.net`` via ``app.services.jwt_verifier`` instead of the
legacy HS256 self-signed tokens from ``auth_service.py``. The returned
principal is a ``CurrentUser`` pydantic model — **not** a SQLAlchemy ``User``
— so callers that used ``user.id: uuid.UUID`` / ``user.username`` must update
to the new field names and string ``id``.

Callers that are currently broken by this change are migrated in Phase 2
Group B.
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.current_user import CurrentUser
from app.services.jwt_verifier import verify_jwt

_bearer_required = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_required),
) -> CurrentUser:
    """Verify the JWT and enforce admin-only access on the /api/v1 surface.

    Raises:
        HTTPException 401 — missing/invalid/expired token (via ``verify_jwt``
            or ``HTTPBearer`` auto_error).
        HTTPException 403 — token valid but user is not admin or is
            deactivated.
    """
    payload = await verify_jwt(credentials.credentials)
    user = CurrentUser.from_payload(payload)
    if user.role != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Admin access required"
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User deactivated")
    return user


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Use rightmost IP — the one added by our reverse proxy (not client-controlled)
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
