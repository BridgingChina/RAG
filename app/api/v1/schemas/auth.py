"""Authentication schemas.

Phase 2: login/logout/password/JWT-issue moved to auth.bridgingchina.net.
FastAPI only projects the verified JWT payload via ``/api/v1/auth/me``; the
legacy ``LoginRequest``/``LoginResponse``/``ChangePasswordRequest`` models
were deleted alongside the endpoints that consumed them.
"""
from typing import Optional

from pydantic import BaseModel


class UserInfo(BaseModel):
    """Projection of the verified Better Auth JWT payload.

    ``id`` is the Better Auth user.id (base64url string), NOT a UUID —
    mirrors ``CurrentUser`` in ``app.models.current_user``.
    """

    id: str
    email: str
    role: str = "user"
    username: Optional[str] = None
    name: Optional[str] = None
