"""CurrentUser — authenticated principal reconstructed from a JWT payload.

This is NOT a SQLAlchemy model. The user record lives in the auth Worker's
D1 database now; the FastAPI side just reconstructs enough fields from the
verified JWT to enforce authorisation. Intentionally not exported from
``app.models.__init__`` because that module re-exports ORM tables.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError


class CurrentUser(BaseModel):
    """Pydantic model for a Better Auth user projected from a verified JWT.

    The ``id`` field is the Better Auth ``user.id`` — a 32-char base64url
    string, NOT a UUID. Callers migrating from the legacy SQLAlchemy ``User``
    model (which used ``uuid.UUID``) must switch to strings.
    """

    id: str  # Better Auth user.id string (~32-char base64url)
    email: str
    email_verified: bool = False
    role: str = "user"  # 'admin' | 'user'
    username: Optional[str] = None
    name: Optional[str] = None
    is_active: bool = True

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "CurrentUser":
        """Construct from a verified JWT payload (as returned by
        ``app.services.jwt_verifier.verify_jwt``).

        Raises ``HTTPException(401)`` when the payload is missing required
        claims (``sub`` / ``email``) or when field types are invalid. This
        matters for public endpoints: ``get_optional_user`` catches
        ``HTTPException`` and degrades to anonymous, so a malformed-but-signed
        token from the auth Worker will not 500 every public request.
        """
        try:
            return cls(
                id=payload["sub"],
                email=payload["email"],
                email_verified=payload.get("emailVerified", False),
                role=payload.get("role", "user"),
                username=payload.get("username"),
                name=payload.get("name"),
                is_active=payload.get("isActive", True),
            )
        except (KeyError, ValidationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing required claims",
            ) from exc
