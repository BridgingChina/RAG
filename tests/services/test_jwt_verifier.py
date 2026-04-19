"""Tests for app.services.jwt_verifier.

These tests generate an ephemeral Ed25519 keypair per-test, mock
``jwks_client.get_key_for_kid`` to return the test public key as a JWK, and
verify tokens signed with the private half.
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

from app.core.config import settings
from app.services import jwt_verifier
from app.services.jwt_verifier import verify_jwt


def _b64url_encode_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture
def ed25519_keypair() -> dict[str, Any]:
    """Generate an ephemeral Ed25519 keypair and a JWK representation of the
    public half."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    x = _b64url_encode_nopad(pub_raw)

    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    kid = "test-kid-abc"
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": x,
        "alg": "EdDSA",
        "kid": kid,
    }
    return {
        "kid": kid,
        "private_pem": priv_pem,
        "jwk": jwk,
    }


def _make_token(
    private_pem: bytes,
    kid: str,
    *,
    iss: str | None = None,
    aud: str | None = None,
    exp_delta: int = 60,
    alg: str = "EdDSA",
    sub: str = "user-123",
) -> str:
    now = int(time.time())
    payload = {
        "sub": sub,
        "email": "fresh.lime5148@mask.401.moe",
        "emailVerified": True,
        "role": "user",
        "isActive": True,
        "iss": iss if iss is not None else settings.jwt_issuer,
        "aud": aud if aud is not None else settings.jwt_audience,
        "iat": now,
        "exp": now + exp_delta,
    }
    return pyjwt.encode(
        payload, private_pem, algorithm=alg, headers={"kid": kid}
    )


@pytest.mark.asyncio
async def test_verify_happy_path(
    ed25519_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_key(kid: str) -> Any:
        assert kid == ed25519_keypair["kid"]
        return ed25519_keypair["jwk"]

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    token = _make_token(
        ed25519_keypair["private_pem"], ed25519_keypair["kid"]
    )
    payload = await verify_jwt(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "fresh.lime5148@mask.401.moe"
    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.jwt_audience


@pytest.mark.asyncio
async def test_verify_rejects_expired_token(
    ed25519_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_key(kid: str) -> Any:
        return ed25519_keypair["jwk"]

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    token = _make_token(
        ed25519_keypair["private_pem"],
        ed25519_keypair["kid"],
        exp_delta=-60,  # already expired 60s ago
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(token)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token expired"


@pytest.mark.asyncio
async def test_verify_rejects_wrong_issuer(
    ed25519_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_key(kid: str) -> Any:
        return ed25519_keypair["jwk"]

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    token = _make_token(
        ed25519_keypair["private_pem"],
        ed25519_keypair["kid"],
        iss="https://evil.example.com",
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(token)
    assert exc_info.value.status_code == 401
    assert "issuer" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_verify_rejects_wrong_audience(
    ed25519_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_key(kid: str) -> Any:
        return ed25519_keypair["jwk"]

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    token = _make_token(
        ed25519_keypair["private_pem"],
        ed25519_keypair["kid"],
        aud="other-service",
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(token)
    assert exc_info.value.status_code == 401
    assert "audience" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_verify_rejects_unknown_kid(
    ed25519_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_key(kid: str) -> Any:
        return None  # no such kid

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    token = _make_token(
        ed25519_keypair["private_pem"], ed25519_keypair["kid"]
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(token)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Unknown key id"


@pytest.mark.asyncio
async def test_verify_rejects_wrong_algorithm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A HS256 token should be rejected at the header stage (alg != EdDSA)."""

    async def fake_get_key(kid: str) -> Any:
        # Should never be called — we reject on alg check first.
        pytest.fail("get_key_for_kid should not have been invoked")

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    now = int(time.time())
    token = pyjwt.encode(
        {"sub": "x", "iat": now, "exp": now + 60},
        "super-secret",
        algorithm="HS256",
        headers={"kid": "some-kid"},
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(token)
    assert exc_info.value.status_code == 401
    assert "header" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_verify_rejects_missing_kid(
    ed25519_keypair: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_get_key(kid: str) -> Any:
        pytest.fail("should not reach JWKS lookup when kid is missing")

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    now = int(time.time())
    token = pyjwt.encode(
        {
            "sub": "x",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now,
            "exp": now + 60,
        },
        ed25519_keypair["private_pem"],
        algorithm="EdDSA",
        # no kid header
    )
    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt(token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_rejects_unparseable_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_key(kid: str) -> Any:
        pytest.fail("should not reach JWKS lookup on garbage token")

    monkeypatch.setattr(jwt_verifier, "get_key_for_kid", fake_get_key)

    with pytest.raises(HTTPException) as exc_info:
        await verify_jwt("not-a-jwt")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token header"
