"""Tests for the new JWKS-backed FastAPI dependencies.

Covers:
  * ``app.api.v1.dependencies.get_current_user`` (admin-only /api/v1 surface)
  * ``app.api.public.v1.dependencies.get_optional_user``
  * ``app.api.public.v1.dependencies.require_user``

Shares the Ed25519 fixture pattern with ``test_jwt_verifier.py`` — sign an
ephemeral test keypair, patch ``get_key_for_kid`` to return the public half.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.public.v1 import dependencies as public_deps
from app.api.v1 import dependencies as admin_deps
from app.core.config import settings
from app.services import jwt_verifier


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


@pytest.fixture
def ed25519_setup(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Generate a keypair and patch ``get_key_for_kid`` in the verifier."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    x = _b64url(pub_raw)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    kid = "dep-test-kid"
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": x,
        "alg": "EdDSA",
        "kid": kid,
    }

    async def fake_get_key_for_kid(requested_kid: str) -> Any:
        if requested_kid == kid:
            return jwk
        return None

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key_for_kid)

    return {"kid": kid, "private_pem": priv_pem}


def _make_token(
    setup: dict[str, Any],
    *,
    role: str = "user",
    is_active: bool = True,
    sub: str = "user-xyz",
    email: str = "someone@example.com",
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "emailVerified": True,
        "role": role,
        "isActive": is_active,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + 300,
    }
    return pyjwt.encode(
        payload,
        setup["private_pem"],
        algorithm="EdDSA",
        headers={"kid": setup["kid"]},
    )


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ---------------------------------------------------------------------------
# admin /api/v1 get_current_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_get_current_user_allows_admin(
    ed25519_setup: dict[str, Any],
) -> None:
    token = _make_token(ed25519_setup, role="admin", sub="admin-42")
    user = await admin_deps.get_current_user(credentials=_bearer(token))
    assert user.id == "admin-42"
    assert user.role == "admin"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_admin_get_current_user_rejects_non_admin(
    ed25519_setup: dict[str, Any],
) -> None:
    token = _make_token(ed25519_setup, role="user")
    with pytest.raises(HTTPException) as exc_info:
        await admin_deps.get_current_user(credentials=_bearer(token))
    assert exc_info.value.status_code == 403
    assert "admin" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_admin_get_current_user_rejects_inactive_admin(
    ed25519_setup: dict[str, Any],
) -> None:
    token = _make_token(ed25519_setup, role="admin", is_active=False)
    with pytest.raises(HTTPException) as exc_info:
        await admin_deps.get_current_user(credentials=_bearer(token))
    assert exc_info.value.status_code == 403
    assert "deactivated" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_admin_get_current_user_rejects_invalid_token(
    ed25519_setup: dict[str, Any],
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await admin_deps.get_current_user(credentials=_bearer("garbage"))
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# public /v1 get_optional_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optional_user_returns_none_without_credentials() -> None:
    user = await public_deps.get_optional_user(credentials=None)
    assert user is None


@pytest.mark.asyncio
async def test_optional_user_returns_user_for_valid_token(
    ed25519_setup: dict[str, Any],
) -> None:
    token = _make_token(ed25519_setup, role="user", sub="user-opt")
    user = await public_deps.get_optional_user(credentials=_bearer(token))
    assert user is not None
    assert user.id == "user-opt"
    assert user.role == "user"


@pytest.mark.asyncio
async def test_optional_user_returns_none_for_invalid_token(
    ed25519_setup: dict[str, Any],
) -> None:
    # A malformed token must not crash the request on a public endpoint.
    user = await public_deps.get_optional_user(credentials=_bearer("broken"))
    assert user is None


@pytest.mark.asyncio
async def test_optional_user_anonymises_deactivated_user(
    ed25519_setup: dict[str, Any],
) -> None:
    token = _make_token(ed25519_setup, role="user", is_active=False)
    user = await public_deps.get_optional_user(credentials=_bearer(token))
    assert user is None


# ---------------------------------------------------------------------------
# public /v1 require_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_user_raises_when_no_credentials() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await public_deps.require_user(user=None)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_user_returns_user_when_present(
    ed25519_setup: dict[str, Any],
) -> None:
    token = _make_token(ed25519_setup, role="user", sub="req-user")
    cu = await public_deps.get_optional_user(credentials=_bearer(token))
    out = await public_deps.require_user(user=cu)
    assert out.id == "req-user"
