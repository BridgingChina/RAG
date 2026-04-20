"""Public API dependencies — Phase 2: JWT-only, no more X-Device-Id.

Endpoints that want per-user state use ``Depends(get_optional_user)`` for
"auth if present, anonymous otherwise" or ``Depends(require_user)`` for
"401 unless authenticated".

The legacy ``require_device_id`` dependency was removed together with the
``device_*`` tables in schema v11 — all consumers (favorites / review /
history) switched to ``require_user`` in Group D.
"""
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.current_user import CurrentUser
from app.services.jwt_verifier import verify_jwt

_bearer_optional = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
) -> Optional[CurrentUser]:
    """Return a CurrentUser if a valid JWT is present, else ``None``.

    An invalid / expired token is treated as anonymous rather than an error,
    because these endpoints are public and should keep serving data to
    signed-out callers. Deactivated users are also anonymised.
    """
    if credentials is None:
        return None
    try:
        payload = await verify_jwt(credentials.credentials)
        user = CurrentUser.from_payload(payload)
    except HTTPException:
        return None
    if not user.is_active:
        return None
    return user


async def require_user(
    user: Optional[CurrentUser] = Depends(get_optional_user),
) -> CurrentUser:
    """Require a signed-in user — raise 401 if none is present."""
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Authentication required"
        )
    return user
