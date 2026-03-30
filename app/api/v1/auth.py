"""Authentication API endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_client_ip, get_current_user
from app.api.v1.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserInfo,
)
from app.core.database import get_db
from app.models import User
from app.services.audit_service import AuditService
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate and return access token."""
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        AuditService.log(
            db,
            action=AuditService.LOGIN_FAILURE,
            resource_type="auth",
            detail={"username": body.username[:64]},
            ip_address=get_client_ip(request),
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    token = create_access_token(user_id=user.id, username=user.username)
    AuditService.log(
        db,
        action=AuditService.LOGIN,
        resource_type="auth",
        user_id=user.id,
        ip_address=get_client_ip(request),
    )
    db.commit()
    return LoginResponse(
        access_token=token,
        user=UserInfo(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
    )


@router.get("/me", response_model=UserInfo)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserInfo(
        id=current_user.id,
        username=current_user.username,
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.put("/password")
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.hashed_password = hash_password(body.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    AuditService.log(
        db,
        action=AuditService.CHANGE_PASSWORD,
        resource_type="auth",
        user_id=current_user.id,
        ip_address=get_client_ip(request),
    )
    db.commit()
    return {"message": "Password changed successfully"}
