"""Authentication service — password hashing and JWT token management."""

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(user_id: uuid.UUID, username: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.access_token_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def is_token_valid_for_user(payload: dict, password_changed_at: datetime | None) -> bool:
    """Check that a token was issued after the user's last password change.

    Returns True if the token is still valid (i.e. issued after the password
    change, or no password change has occurred).
    """
    if password_changed_at is None:
        return True
    iat = payload.get("iat")
    if iat is None:
        # Tokens without iat are considered invalid if password was ever changed
        return False
    # iat is a Unix timestamp (int/float) from JWT decode
    token_issued = datetime.fromtimestamp(iat, tz=timezone.utc)
    # Truncate to seconds to avoid sub-second race conditions
    return token_issued >= password_changed_at.replace(microsecond=0)
