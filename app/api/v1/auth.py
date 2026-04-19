"""Authentication API endpoints — Phase 2 projection-only surface.

Login/logout/password flows moved to ``auth.bridgingchina.net`` (Better Auth).
The only admin-side endpoint that remains is ``GET /api/v1/auth/me``, which
projects the verified JWT payload so the admin console can render the
current user without an extra round-trip to the auth Worker.
"""
from fastapi import APIRouter, Depends

from app.api.v1.dependencies import get_current_user
from app.api.v1.schemas.auth import UserInfo
from app.models.current_user import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserInfo)
def get_me(current_user: CurrentUser = Depends(get_current_user)) -> UserInfo:
    return UserInfo(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        username=current_user.username,
        name=current_user.name,
    )
