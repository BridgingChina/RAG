"""Authentication API endpoints."""

import time
import threading
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

# ---------------------------------------------------------------------------
# In-memory login rate limiter
# ---------------------------------------------------------------------------
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 15 * 60  # 15 minutes

# {ip: [timestamp, ...]}  – only failed attempt timestamps within the window
_failed_attempts: dict[str, list[float]] = {}
_lock = threading.Lock()


def _cleanup_and_check(ip: str) -> bool:
    """Remove stale entries and return True if the IP is currently locked out."""
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        # Prune expired entries across all IPs (cheap amortised cleanup)
        stale_ips = [k for k, v in _failed_attempts.items() if v[-1] < cutoff]
        for k in stale_ips:
            del _failed_attempts[k]

        attempts = _failed_attempts.get(ip)
        if attempts is None:
            return False

        # Drop timestamps outside the window
        _failed_attempts[ip] = [t for t in attempts if t >= cutoff]
        if not _failed_attempts[ip]:
            del _failed_attempts[ip]
            return False

        return len(_failed_attempts[ip]) >= _MAX_ATTEMPTS


def _record_failure(ip: str) -> None:
    now = time.monotonic()
    with _lock:
        _failed_attempts.setdefault(ip, []).append(now)


def _reset(ip: str) -> None:
    with _lock:
        _failed_attempts.pop(ip, None)


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate and return access token."""
    client_ip = get_client_ip(request)

    # Check rate limit before processing
    if _cleanup_and_check(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
        )

    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.hashed_password):
        _record_failure(client_ip)
        AuditService.log(
            db,
            action=AuditService.LOGIN_FAILURE,
            resource_type="auth",
            detail={"username": body.username[:64]},
            ip_address=client_ip,
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
    # Successful login — clear rate limit for this IP
    _reset(client_ip)
    token = create_access_token(user_id=user.id, username=user.username)
    AuditService.log(
        db,
        action=AuditService.LOGIN,
        resource_type="auth",
        user_id=user.id,
        ip_address=client_ip,
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
