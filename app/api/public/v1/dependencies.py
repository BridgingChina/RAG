"""Public API dependencies.

Phase 2 introduces optional JWT auth on the C-side (``/v1/*``). Endpoints
that want per-user state can ``Depends(get_optional_user)`` for "auth if
present, anonymous otherwise" or ``Depends(require_user)`` for "401 unless
authenticated".

The legacy ``require_device_id`` dependency is kept for backward
compatibility with favorites / review / history endpoints, which Phase 2
Group D migrates to ``require_user``. **Do not remove until then**, or those
endpoints will break their import graph.

Threat model for X-Device-Id
-----------------------------
X-Device-Id is a client-generated UUID v4 sent via HTTP header. It is NOT
a secret and provides NO authentication — any client that knows (or guesses)
another device's UUID can impersonate it. This is an accepted trade-off for
a public educational app with no user accounts on the consumer (C 端) side:

- **What it guards:** favorites, review progress, and view history are
  partitioned by device_id so that one device's data does not leak into
  another's responses by default.
- **What it does NOT guard:** a malicious actor who obtains or brute-forces
  a device_id can read and modify that device's favorites/progress/history.
  Since this data has no PII and no monetary value, the risk is low.
- **Mitigation if needed later:** add HMAC signing of the device_id (e.g.
  ``X-Device-Id-Sig``) or migrate to a lightweight auth token.

All endpoints that accept X-Device-Id MUST include device_id in their
database WHERE clauses so that a request can only read/write rows belonging
to the presented device_id (ownership scoping).
"""
import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
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
        # Invalid token (bad sig, expired, wrong iss/aud, missing required
        # claims) on an optional endpoint -> treat as anonymous. Keeps the
        # public API serving data to signed-out callers even if the auth
        # Worker briefly ships a malformed-but-signed payload.
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


# ---------------------------------------------------------------------------
# Legacy: X-Device-Id header (DEPRECATED).
#
# ``require_device_id`` is used by favorites.py / review.py / history.py which
# are still on the old code path. Phase 2 Group D migrates those endpoints to
# ``require_user`` and then removes this helper. Until then, **do not delete**
# — removing it will break imports in the three modules above.
# ---------------------------------------------------------------------------


def require_device_id(x_device_id: str = Header(...)) -> uuid.UUID:
    """Validate X-Device-Id header format (UUID v4) and return it.

    Security note: this only validates *format* — it does not authenticate
    the caller. See module docstring for the full threat model.
    """
    try:
        parsed = uuid.UUID(x_device_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid X-Device-Id format")
    if parsed.version != 4:
        raise HTTPException(400, detail="X-Device-Id must be UUID v4")
    return parsed
