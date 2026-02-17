# P3 — Auth & Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add JWT authentication and write-operation audit logging to the Bridge RAG team panel.

**Architecture:** Backend adds `users` + `audit_logs` tables, JWT auth via `python-jose` + `passlib`, FastAPI dependency injection for route protection. Frontend adds login page, AuthGuard wrapper, token management in api.ts, and audit log viewer page.

**Tech Stack:** python-jose[cryptography], passlib[bcrypt] (backend); existing React + React Router + shadcn/ui (frontend)

**Design deviation:** `users.id` uses `int` (not UUID) to match codebase convention. `audit_logs.user_id` is `int | null` accordingly.

---

### Task 1: Add Python Dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add auth dependencies to pyproject.toml**

In the `dependencies` list, add:

```python
"python-jose[cryptography]>=3.3.0",
"passlib[bcrypt]>=1.7.4",
```

**Step 2: Install dependencies**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed python-jose and passlib

**Step 3: Verify imports work**

Run: `python3 -c "from jose import jwt; from passlib.context import CryptContext; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat(auth): add python-jose and passlib dependencies"
```

---

### Task 2: Add SECRET_KEY to Settings

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

**Step 1: Add SECRET_KEY to Settings class**

In `app/core/config.py`, add to the `Settings` class:

```python
# Auth settings
secret_key: str = "change-me-in-production"
access_token_expire_hours: int = 24
```

**Step 2: Add to .env.example**

```
SECRET_KEY=change-me-in-production
```

**Step 3: Verify settings load**

Run: `python3 -c "from app.core.config import settings; print(settings.secret_key)"`
Expected: `change-me-in-production`

**Step 4: Commit**

```bash
git add app/core/config.py .env.example
git commit -m "feat(auth): add SECRET_KEY and token expiry to settings"
```

---

### Task 3: User and AuditLog Models

**Files:**
- Create: `app/models/user.py`
- Create: `app/models/audit_log.py`
- Modify: `app/models/__init__.py`

**Step 1: Write test — verify models importable**

Create `tests/test_models_auth.py`:

```python
"""Tests for auth-related models."""


def test_user_model_importable():
    from app.models import User
    assert User.__tablename__ == "users"


def test_audit_log_model_importable():
    from app.models import AuditLog
    assert AuditLog.__tablename__ == "audit_logs"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_auth.py -v`
Expected: FAIL — ImportError

**Step 3: Create User model**

Create `app/models/user.py`:

```python
"""User model for authentication."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

**Step 4: Create AuditLog model**

Create `app/models/audit_log.py`:

```python
"""Audit log model for tracking write operations."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_id", "user_id"),
    )
```

**Step 5: Register in models __init__.py**

In `app/models/__init__.py`, add imports:

```python
from app.models.user import User
from app.models.audit_log import AuditLog
```

Add `"User"` and `"AuditLog"` to `__all__`.

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_models_auth.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add app/models/user.py app/models/audit_log.py app/models/__init__.py tests/test_models_auth.py
git commit -m "feat(auth): add User and AuditLog database models"
```

---

### Task 4: Auth Service (password hashing + JWT)

**Files:**
- Create: `app/services/auth_service.py`

**Step 1: Write test**

Create `tests/test_auth_service.py`:

```python
"""Tests for auth service — password hashing and JWT."""

from app.services.auth_service import hash_password, verify_password, create_access_token, decode_access_token


def test_hash_and_verify_password():
    hashed = hash_password("testpass123")
    assert hashed != "testpass123"
    assert verify_password("testpass123", hashed) is True
    assert verify_password("wrongpass", hashed) is False


def test_create_and_decode_token():
    token = create_access_token(user_id=1, username="admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "1"
    assert payload["username"] == "admin"


def test_decode_invalid_token():
    payload = decode_access_token("invalid.token.here")
    assert payload is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth_service.py -v`
Expected: FAIL — ImportError

**Step 3: Implement auth service**

Create `app/services/auth_service.py`:

```python
"""Authentication service — password hashing and JWT token management."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/auth_service.py tests/test_auth_service.py
git commit -m "feat(auth): implement password hashing and JWT service"
```

---

### Task 5: Auth Schemas

**Files:**
- Create: `app/api/v1/schemas/auth.py`
- Modify: `app/api/v1/schemas/__init__.py`

**Step 1: Create auth schemas**

Create `app/api/v1/schemas/auth.py`:

```python
"""Authentication schemas."""

from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str | None
    is_active: bool
    created_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
```

**Step 2: Add to schemas __init__.py**

In `app/api/v1/schemas/__init__.py`, add:

```python
# Auth schemas
from .auth import ChangePasswordRequest, LoginRequest, LoginResponse, UserInfo
```

And add to `__all__`.

**Step 3: Verify import**

Run: `python3 -c "from app.api.v1.schemas import LoginRequest, LoginResponse; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add app/api/v1/schemas/auth.py app/api/v1/schemas/__init__.py
git commit -m "feat(auth): add auth Pydantic schemas"
```

---

### Task 6: Auth API Endpoints

**Files:**
- Create: `app/api/v1/auth.py`
- Create: `app/api/v1/dependencies.py`

**Step 1: Write test**

Create `tests/test_api_v1_auth.py`:

```python
"""Tests for V1 Auth API endpoints."""

from app.main import app


def test_auth_login_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/login" in route_paths


def test_auth_me_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/me" in route_paths


def test_auth_password_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/auth/password" in route_paths


def test_login_rejects_missing_credentials():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422


def test_me_rejects_unauthenticated():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_v1_auth.py -v`
Expected: FAIL

**Step 3: Create auth dependencies**

Create `app/api/v1/dependencies.py`:

```python
"""Shared API dependencies."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import User
from app.services.auth_service import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = int(payload["sub"])
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
```

**Step 4: Create auth endpoints**

Create `app/api/v1/auth.py`:

```python
"""Authentication API endpoints."""

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
from app.services.auth_service import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return access token."""
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.hashed_password):
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
    db.commit()
    return {"message": "Password changed successfully"}
```

**Step 5: Register auth router in v1 __init__.py**

In `app/api/v1/__init__.py`, add:

```python
from app.api.v1.auth import router as auth_router
```

And add `router.include_router(auth_router)`.

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_api_v1_auth.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add app/api/v1/auth.py app/api/v1/dependencies.py tests/test_api_v1_auth.py app/api/v1/__init__.py
git commit -m "feat(auth): implement login, me, change-password endpoints"
```

---

### Task 7: Protect Existing Routes with Auth

**Files:**
- Modify: `app/api/v1/__init__.py`

**Step 1: Write test**

Add to `tests/test_api_v1_auth.py`:

```python
def test_protected_routes_reject_unauthenticated():
    """All non-auth API routes should require authentication."""
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)

    protected_gets = [
        "/api/v1/chunks",
        "/api/v1/bridges",
        "/api/v1/sources",
        "/api/v1/stats/dashboard",
    ]
    for path in protected_gets:
        response = client.get(path)
        assert response.status_code == 401, f"{path} should be protected"


def test_health_remains_public():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/health")
    assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_v1_auth.py::test_protected_routes_reject_unauthenticated -v`
Expected: FAIL — routes return 200 without auth

**Step 3: Add auth dependency to v1 router**

Restructure `app/api/v1/__init__.py` to apply `get_current_user` as a dependency on the protected router:

```python
"""V1 API routes."""

from fastapi import APIRouter, Depends

from app.api.v1.auth import router as auth_router
from app.api.v1.ask import router as ask_router
from app.api.v1.bridges import router as bridges_router
from app.api.v1.chunks import router as chunks_router
from app.api.v1.ingest import router as ingest_router
from app.api.v1.sources import router as sources_router
from app.api.v1.stats import router as stats_router
from app.api.v1.system import router as system_router
from app.api.v1.taxonomy import router as taxonomy_router
from app.api.v1.dependencies import get_current_user

router = APIRouter()

# Public routes (no auth required)
router.include_router(auth_router)

# Protected routes (auth required)
protected = APIRouter(dependencies=[Depends(get_current_user)])
protected.include_router(ask_router)
protected.include_router(bridges_router)
protected.include_router(chunks_router)
protected.include_router(ingest_router)
protected.include_router(sources_router)
protected.include_router(stats_router)
protected.include_router(system_router)
protected.include_router(taxonomy_router)

router.include_router(protected)

__all__ = ["router"]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_api_v1_auth.py -v`
Expected: PASS

**Step 5: Run all existing tests to check for breakage**

Run: `pytest tests/ -v`
Expected: Some existing smoke tests that call protected endpoints without auth may now get 401 instead of 200. Update those tests to expect 401 or to skip auth check. Specifically, tests that use `TestClient` to call endpoints like `POST /bridges` will now get 401 — this is correct behavior. Adjust assertions from `not in (404, 405)` to `not in (404, 405)` OR `== 401` as needed.

**Step 6: Fix any broken tests**

For tests that verify "endpoint accepts POST" like `test_bridges_create_accepts_post`, update assertion:

```python
def test_bridges_create_accepts_post():
    from fastapi.testclient import TestClient
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/v1/bridges", json={"name": "测试桥"})
    # 401 (no auth) is fine — proves endpoint exists and accepts POST (not 404/405)
    assert response.status_code not in (404, 405)
```

This assertion already works since 401 is not in (404, 405). Verify all tests pass.

**Step 7: Commit**

```bash
git add app/api/v1/__init__.py tests/
git commit -m "feat(auth): protect all API routes except /auth/login"
```

---

### Task 8: Audit Service

**Files:**
- Create: `app/services/audit_service.py`

**Step 1: Write test**

Create `tests/test_audit_service.py`:

```python
"""Tests for audit service."""

from app.services.audit_service import AuditService


def test_audit_service_importable():
    assert callable(AuditService.log)


def test_audit_log_action_constants():
    """Verify action constants are defined."""
    assert AuditService.LOGIN == "login"
    assert AuditService.LOGIN_FAILURE == "login_failure"
    assert AuditService.CREATE == "create"
    assert AuditService.UPDATE == "update"
    assert AuditService.DELETE == "delete"
    assert AuditService.MERGE == "merge"
    assert AuditService.INGEST == "ingest"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_service.py -v`
Expected: FAIL — ImportError

**Step 3: Implement audit service**

Create `app/services/audit_service.py`:

```python
"""Audit logging service for tracking write operations."""

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    # Action constants
    LOGIN = "login"
    LOGIN_FAILURE = "login_failure"
    CHANGE_PASSWORD = "change_password"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"
    INGEST = "ingest"
    BATCH_UPDATE = "batch_update"

    @staticmethod
    def log(
        db: Session,
        *,
        action: str,
        resource_type: str,
        user_id: int | None = None,
        resource_id: str | None = None,
        detail: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
        )
        db.add(entry)
        db.flush()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/services/audit_service.py tests/test_audit_service.py
git commit -m "feat(audit): implement audit logging service"
```

---

### Task 9: Wire Audit into Auth Endpoints

**Files:**
- Modify: `app/api/v1/auth.py`

**Step 1: Add audit logging to login endpoint**

In `app/api/v1/auth.py`, import audit service and `get_client_ip`, then add audit calls:

In `login()`:
- On success: `AuditService.log(db, action=AuditService.LOGIN, resource_type="auth", user_id=user.id, ip_address=get_client_ip(request))`
- On failure: `AuditService.log(db, action=AuditService.LOGIN_FAILURE, resource_type="auth", detail={"username": body.username}, ip_address=get_client_ip(request))` — call this **before** raising HTTPException, and `db.commit()` so it persists.

Add `request: Request` parameter to `login()`.

In `change_password()`:
- On success: `AuditService.log(db, action=AuditService.CHANGE_PASSWORD, resource_type="auth", user_id=current_user.id, ip_address=get_client_ip(request))`

Add `request: Request` parameter to `change_password()`.

**Step 2: Verify login still works**

Run: `pytest tests/test_api_v1_auth.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add app/api/v1/auth.py
git commit -m "feat(audit): add audit logging to auth endpoints"
```

---

### Task 10: Wire Audit into CRUD Endpoints

**Files:**
- Modify: `app/api/v1/bridges.py`
- Modify: `app/api/v1/chunks.py`
- Modify: `app/api/v1/ingest.py`
- Modify: `app/api/v1/taxonomy.py`
- Modify: `app/api/v1/system.py`

**Step 1: Add audit to bridges.py**

Add imports:
```python
from app.api.v1.dependencies import get_current_user, get_client_ip
from app.models import User
from app.services.audit_service import AuditService
```

For each write endpoint, add `current_user: User = Depends(get_current_user)` and `request: Request` parameters (note: `get_current_user` is already applied via the protected router dependency, but we need the user object explicitly here).

Add audit calls after successful DB operations:
- `create_bridge`: `AuditService.log(db, action=AuditService.CREATE, resource_type="bridge", user_id=current_user.id, resource_id=str(bridge.id), ip_address=get_client_ip(request))`
- `update_bridge`: `AuditService.log(db, action=AuditService.UPDATE, resource_type="bridge", ...)`
- `delete_bridge`: `AuditService.log(db, action=AuditService.DELETE, resource_type="bridge", ...)`
- `merge_bridge`: `AuditService.log(db, action=AuditService.MERGE, resource_type="bridge", user_id=current_user.id, resource_id=str(target_id), detail={"source_bridge_id": body.source_bridge_id}, ...)`

**Step 2: Add audit to chunks.py**

Same pattern for `delete_chunk` (and `update_chunk` if it exists).

**Step 3: Add audit to ingest.py**

After successful ingest: `AuditService.log(db, action=AuditService.INGEST, resource_type="source", user_id=current_user.id, resource_id=str(source.id), detail={"title": source.title, "chunk_count": len(chunks)}, ...)`

**Step 4: Add audit to taxonomy.py**

For `create_node`, `update_node`, `delete_node`, `batch_update`.

**Step 5: Add audit to system.py**

For settings update (if PUT endpoint exists).

**Step 6: Run all tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 7: Commit**

```bash
git add app/api/v1/bridges.py app/api/v1/chunks.py app/api/v1/ingest.py app/api/v1/taxonomy.py app/api/v1/system.py
git commit -m "feat(audit): wire audit logging into all write endpoints"
```

---

### Task 11: Audit Log Query Endpoint + Schema

**Files:**
- Create: `app/api/v1/schemas/audit.py`
- Modify: `app/api/v1/schemas/__init__.py`
- Create: `app/api/v1/audit.py`
- Modify: `app/api/v1/__init__.py`

**Step 1: Write test**

Create `tests/test_api_v1_audit.py`:

```python
"""Tests for V1 Audit Log API endpoint."""

from app.main import app


def test_audit_logs_endpoint_exists():
    route_paths = [route.path for route in app.routes]
    assert "/api/v1/audit-logs" in route_paths


def test_audit_logs_requires_auth():
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/audit-logs")
    assert response.status_code == 401
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_v1_audit.py -v`
Expected: FAIL

**Step 3: Create audit schemas**

Create `app/api/v1/schemas/audit.py`:

```python
"""Audit log schemas."""

from datetime import datetime

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: int | None
    username: str | None
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    created_at: datetime
```

Add to `app/api/v1/schemas/__init__.py`.

**Step 4: Create audit endpoint**

Create `app/api/v1/audit.py`:

```python
"""Audit log API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.v1.schemas.audit import AuditLogItem
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogItem])
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuditLogItem]:
    """List audit logs with optional filters."""
    query = db.query(
        AuditLog.id,
        AuditLog.user_id,
        User.username,
        AuditLog.action,
        AuditLog.resource_type,
        AuditLog.resource_id,
        AuditLog.detail,
        AuditLog.ip_address,
        AuditLog.created_at,
    ).outerjoin(User, AuditLog.user_id == User.id)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if resource_type is not None:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start is not None:
        query = query.filter(AuditLog.created_at >= start)
    if end is not None:
        query = query.filter(AuditLog.created_at <= end)

    total = query.count()
    offset = (page - 1) * page_size
    results = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size).all()

    items = [
        AuditLogItem(
            id=row.id,
            user_id=row.user_id,
            username=row.username,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            detail=row.detail,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in results
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )
```

**Step 5: Register audit router in protected group**

In `app/api/v1/__init__.py`, import `audit_router` and add to `protected`.

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_api_v1_audit.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add app/api/v1/schemas/audit.py app/api/v1/schemas/__init__.py app/api/v1/audit.py app/api/v1/__init__.py tests/test_api_v1_audit.py
git commit -m "feat(audit): add audit log query endpoint with filters"
```

---

### Task 12: Create User CLI Script

**Files:**
- Create: `scripts/create_user.py`

**Step 1: Create the script**

```python
"""CLI script to create a user account."""

import argparse
import sys

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import User
from app.services.auth_service import hash_password


def create_user(username: str, password: str, display_name: str | None = None) -> None:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)

        user = User(
            username=username,
            hashed_password=hash_password(password),
            display_name=display_name,
        )
        db.add(user)
        db.commit()
        print(f"User '{username}' created successfully (id={user.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a user account")
    parser.add_argument("--username", required=True, help="Username")
    parser.add_argument("--password", required=True, help="Password")
    parser.add_argument("--display-name", help="Display name (optional)")
    args = parser.parse_args()

    create_user(args.username, args.password, args.display_name)
```

**Step 2: Verify script is parseable**

Run: `python3 scripts/create_user.py --help`
Expected: Shows help text with --username and --password options

**Step 3: Commit**

```bash
git add scripts/create_user.py
git commit -m "feat(auth): add create_user CLI script"
```

---

### Task 13: Database Migration — Add New Tables

**Files:**
- Modify: `app/core/database.py`

**Step 1: Bump schema version**

In `app/core/database.py`:
- Update `LATEST_SCHEMA_VERSION` to `3`
- In `init_database()`, after `Base.metadata.create_all(conn)`, the new tables will be auto-created for fresh installs
- Add a migration path for existing v2 databases: if `current_version == 2`, create the new tables and set version to 3

Add migration logic:

```python
if current_version == 2:
    logger.info("Migrating schema v2 → v3: adding users and audit_logs tables...")
    from app.models.user import User
    from app.models.audit_log import AuditLog
    User.__table__.create(conn, checkfirst=True)
    AuditLog.__table__.create(conn, checkfirst=True)
    set_schema_version(engine, 3, "Add users and audit_logs tables", conn=conn)
    logger.info("Migration to v3 complete.")
    return
```

**Step 2: Also update migrate_db.py if it exists**

Check `scripts/migrate_db.py` and add the v2→v3 migration there as well.

**Step 3: Run tests**

Run: `pytest tests/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add app/core/database.py scripts/migrate_db.py
git commit -m "feat(auth): schema v3 migration — users and audit_logs tables"
```

---

### Task 14: Frontend — Auth Types + API Functions

**Files:**
- Modify: `web/src/lib/types.ts`
- Modify: `web/src/lib/api.ts`

**Step 1: Add auth types**

In `web/src/lib/types.ts`, add:

```typescript
// Auth
export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface UserInfo {
  id: number
  username: string
  display_name: string | null
  is_active: boolean
  created_at: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

// Audit
export interface AuditLogItem {
  id: number
  user_id: number | null
  username: string | null
  action: string
  resource_type: string
  resource_id: string | null
  detail: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}
```

**Step 2: Modify api.ts — add auth header to all requests**

In `web/src/lib/api.ts`, create a helper to get auth headers:

```typescript
function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("auth-token")
  if (token) {
    return { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
  }
  return { "Content-Type": "application/json" }
}
```

Replace hardcoded `headers: { "Content-Type": "application/json" }` in `get`, `post`, `put`, `del` with `headers: authHeaders()`.

Add 401 handling — in the error check of each function, before throwing:

```typescript
if (res.status === 401) {
  localStorage.removeItem("auth-token")
  window.location.href = "/login"
  throw new Error("Unauthorized")
}
```

**Step 3: Add auth API functions**

```typescript
export function login(data: LoginRequest): Promise<LoginResponse> {
  // Use raw fetch to avoid auth header (not logged in yet)
  return fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `HTTP ${res.status}`)
    }
    return res.json()
  })
}

export function fetchMe(): Promise<UserInfo> {
  return get<UserInfo>("/auth/me")
}

export function changePassword(data: ChangePasswordRequest): Promise<void> {
  return put<void>("/auth/password", data)
}

export function fetchAuditLogs(params?: {
  page?: number
  page_size?: number
  user_id?: number
  action?: string
  resource_type?: string
  start?: string
  end?: string
}): Promise<PaginatedResponse<AuditLogItem>> {
  return get<PaginatedResponse<AuditLogItem>>("/audit-logs", params)
}
```

**Step 4: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 5: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/api.ts
git commit -m "feat(auth): add auth types, API functions, and token management"
```

---

### Task 15: Frontend — AuthContext + AuthGuard

**Files:**
- Create: `web/src/contexts/AuthContext.tsx`
- Create: `web/src/components/auth/AuthGuard.tsx`

**Step 1: Create AuthContext**

Create `web/src/contexts/AuthContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import { fetchMe } from "@/lib/api"
import type { UserInfo } from "@/lib/types"

interface AuthContextType {
  user: UserInfo | null
  setUser: (user: UserInfo | null) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)

  const logout = () => {
    localStorage.removeItem("auth-token")
    setUser(null)
    window.location.href = "/login"
  }

  return (
    <AuthContext.Provider value={{ user, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
```

**Step 2: Create AuthGuard**

Create `web/src/components/auth/AuthGuard.tsx`:

```tsx
import { useEffect, useState } from "react"
import { Outlet, useNavigate } from "react-router"
import { fetchMe } from "@/lib/api"
import { useAuth } from "@/contexts/AuthContext"

export function AuthGuard() {
  const navigate = useNavigate()
  const { setUser } = useAuth()
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem("auth-token")
    if (!token) {
      navigate("/login", { replace: true })
      return
    }
    fetchMe()
      .then((user) => {
        setUser(user)
        setChecking(false)
      })
      .catch(() => {
        localStorage.removeItem("auth-token")
        navigate("/login", { replace: true })
      })
  }, [navigate, setUser])

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">验证中...</p>
      </div>
    )
  }

  return <Outlet />
}
```

**Step 3: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 4: Commit**

```bash
git add web/src/contexts/AuthContext.tsx web/src/components/auth/AuthGuard.tsx
git commit -m "feat(auth): add AuthContext and AuthGuard components"
```

---

### Task 16: Frontend — Login Page

**Files:**
- Create: `web/src/pages/LoginPage.tsx`

**Step 1: Create LoginPage**

```tsx
import { useState } from "react"
import { useNavigate } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { login } from "@/lib/api"
import { useAuth } from "@/contexts/AuthContext"

export function Component() {
  const navigate = useNavigate()
  const { setUser } = useAuth()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await login({ username, password })
      localStorage.setItem("auth-token", res.access_token)
      setUser(res.user)
      navigate("/", { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">桥梁知识库</CardTitle>
          <p className="text-sm text-muted-foreground">请登录以继续</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">用户名</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "登录中..." : "登录"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add web/src/pages/LoginPage.tsx
git commit -m "feat(auth): add login page"
```

---

### Task 17: Frontend — Router Wiring + Sidebar Update

**Files:**
- Modify: `web/src/router.tsx`
- Modify: `web/src/main.tsx`
- Modify: `web/src/components/layout/DashboardLayout.tsx`
- Modify: `web/src/components/layout/AppSidebar.tsx`

**Step 1: Update router.tsx**

Restructure routes to include AuthGuard and LoginPage:

```tsx
import { createBrowserRouter } from "react-router"
import { AuthGuard } from "@/components/auth/AuthGuard"
import { DashboardLayout } from "@/components/layout/DashboardLayout"

export const router = createBrowserRouter([
  { path: "login", lazy: () => import("@/pages/LoginPage") },
  {
    element: <AuthGuard />,
    children: [
      {
        element: <DashboardLayout />,
        children: [
          { index: true, lazy: () => import("@/pages/DashboardPage") },
          { path: "chunks", lazy: () => import("@/pages/ChunkListPage") },
          { path: "chunks/:id", lazy: () => import("@/pages/ChunkDetailPage") },
          { path: "bridges", lazy: () => import("@/pages/BridgeListPage") },
          { path: "bridges/new", lazy: () => import("@/pages/BridgeCreatePage") },
          { path: "bridges/:id", lazy: () => import("@/pages/BridgeDetailPage") },
          { path: "sources", lazy: () => import("@/pages/SourceListPage") },
          { path: "sources/:id", lazy: () => import("@/pages/SourceDetailPage") },
          { path: "taxonomy", lazy: () => import("@/pages/TaxonomyPage") },
          { path: "ingest", lazy: () => import("@/pages/IngestPage") },
          { path: "ask", lazy: () => import("@/pages/AskPage") },
          { path: "settings", lazy: () => import("@/pages/SettingsPage") },
          { path: "audit-logs", lazy: () => import("@/pages/AuditLogPage") },
        ],
      },
    ],
  },
])
```

**Step 2: Wrap router with AuthProvider in main.tsx**

In `web/src/main.tsx`, wrap `RouterProvider` with `AuthProvider`:

```tsx
import { AuthProvider } from "@/contexts/AuthContext"

// ...
<AuthProvider>
  <RouterProvider router={router} />
</AuthProvider>
```

**Step 3: Add audit log to sidebar**

In `web/src/components/layout/AppSidebar.tsx`:

Add import: `import { ScrollText } from "lucide-react"` (or `ClipboardList`)

Add to the "系统" group in `navGroups`:
```typescript
{ path: "/audit-logs", icon: ScrollText, label: "审计日志" },
```

**Step 4: Add user info + logout to sidebar footer**

In `web/src/components/layout/AppSidebar.tsx`, update the `SidebarFooter`:

```tsx
import { LogOut } from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"

// Inside AppSidebar component:
const { user, logout } = useAuth()

// Replace SidebarFooter content:
<SidebarFooter>
  <SidebarMenu>
    <SidebarMenuItem>
      <SidebarMenuButton size="sm" className="text-muted-foreground">
        {user?.display_name || user?.username || ""}
      </SidebarMenuButton>
    </SidebarMenuItem>
    <SidebarMenuItem>
      <SidebarMenuButton size="sm" onClick={logout} className="text-muted-foreground">
        <LogOut />
        <span>退出登录</span>
      </SidebarMenuButton>
    </SidebarMenuItem>
  </SidebarMenu>
</SidebarFooter>
```

**Step 5: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 6: Commit**

```bash
git add web/src/router.tsx web/src/main.tsx web/src/components/layout/DashboardLayout.tsx web/src/components/layout/AppSidebar.tsx
git commit -m "feat(auth): wire login route, auth guard, sidebar user info"
```

---

### Task 18: Frontend — Audit Log Page

**Files:**
- Create: `web/src/pages/AuditLogPage.tsx`

**Step 1: Create AuditLogPage**

Follow `SourceListPage` pattern with filters for user, action, resource_type, and time range:

```tsx
import { useState } from "react"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useApi } from "@/hooks/useApi"
import { fetchAuditLogs } from "@/lib/api"

const NONE = "__all__"

const ACTION_OPTIONS = [
  { value: NONE, label: "全部操作" },
  { value: "login", label: "登录" },
  { value: "login_failure", label: "登录失败" },
  { value: "create", label: "创建" },
  { value: "update", label: "更新" },
  { value: "delete", label: "删除" },
  { value: "merge", label: "合并" },
  { value: "ingest", label: "入库" },
  { value: "batch_update", label: "批量更新" },
  { value: "change_password", label: "改密码" },
]

const RESOURCE_OPTIONS = [
  { value: NONE, label: "全部资源" },
  { value: "auth", label: "认证" },
  { value: "bridge", label: "桥梁" },
  { value: "chunk", label: "知识块" },
  { value: "source", label: "来源" },
  { value: "taxonomy", label: "分类" },
  { value: "settings", label: "设置" },
]

export function Component() {
  const [page, setPage] = useState(1)
  const [actionFilter, setActionFilter] = useState(NONE)
  const [resourceFilter, setResourceFilter] = useState(NONE)

  const { data, loading, error, refetch } = useApi(
    () =>
      fetchAuditLogs({
        page,
        page_size: 20,
        action: actionFilter === NONE ? undefined : actionFilter,
        resource_type: resourceFilter === NONE ? undefined : resourceFilter,
      }),
    [page, actionFilter, resourceFilter],
  )

  const handleFilterChange = (setter: (v: string) => void) => (value: string) => {
    setter(value)
    setPage(1)
  }

  if (loading) {
    return (
      <>
        <PageHeader title="审计日志" description="查看系统操作记录" />
        <main className="space-y-6 p-6">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-96 w-full" />
        </main>
      </>
    )
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="审计日志" description="查看系统操作记录" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{error || "加载失败"}</p>
            <Button onClick={refetch} variant="outline" size="sm">重试</Button>
          </div>
        </main>
      </>
    )
  }

  const { items, total_pages } = data

  return (
    <>
      <PageHeader title="审计日志" description="查看系统操作记录" />
      <main className="space-y-6 p-6">
        {/* Filters */}
        <div className="flex items-center gap-4">
          <Select value={actionFilter} onValueChange={handleFilterChange(setActionFilter)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ACTION_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={resourceFilter} onValueChange={handleFilterChange(setResourceFilter)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RESOURCE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">暂无审计记录</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>时间</TableHead>
                    <TableHead>用户</TableHead>
                    <TableHead>操作</TableHead>
                    <TableHead>资源类型</TableHead>
                    <TableHead>资源 ID</TableHead>
                    <TableHead>IP</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString("zh-CN")}
                      </TableCell>
                      <TableCell>{log.username || "-"}</TableCell>
                      <TableCell>
                        <Badge variant={log.action === "login_failure" ? "destructive" : "secondary"}>
                          {log.action}
                        </Badge>
                      </TableCell>
                      <TableCell>{log.resource_type}</TableCell>
                      <TableCell className="font-mono text-xs">{log.resource_id || "-"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{log.ip_address || "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            {total_pages > 0 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">第 {page} / {total_pages} 页</p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPage(page - 1)} disabled={page <= 1}>上一页</Button>
                  <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={page >= total_pages}>下一页</Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </>
  )
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Commit**

```bash
git add web/src/pages/AuditLogPage.tsx
git commit -m "feat(audit): add audit log viewer page"
```

---

### Task 19: Run Full Test Suite + Manual Smoke Test

**Step 1: Run all backend tests**

Run: `pytest tests/ -v`
Expected: All PASS

**Step 2: Run frontend type check**

Run: `cd web && npx tsc --noEmit`
Expected: No errors

**Step 3: Run frontend build**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 4: Manual smoke test (if DB is running)**

1. Reset DB: `python3 scripts/reset_db.py --force`
2. Create user: `python3 scripts/create_user.py --username admin --password admin123`
3. Start backend: `uvicorn app.main:app --reload`
4. Start frontend: `cd web && npm run dev`
5. Open `http://localhost:5173` → should redirect to `/login`
6. Login with admin/admin123 → should redirect to dashboard
7. Perform some operations (create bridge, etc.)
8. Check audit logs page → should show entries

**Step 5: Commit any remaining fixes**

```bash
git add -A
git commit -m "fix: resolve any remaining issues from smoke test"
```

---

### Task 20: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add auth-related info to CLAUDE.md**

Add to relevant sections:
- In **API Endpoints**: add auth routes, audit-logs route
- In **Commands**: add `python3 scripts/create_user.py` usage
- In **Data Model**: mention users and audit_logs tables
- In **Environment Setup**: mention SECRET_KEY

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with auth and audit info"
```
