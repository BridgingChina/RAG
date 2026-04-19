"""EdDSA JWT verifier backed by the upstream auth.bridgingchina.net JWKS.

Why PyJWT (not python-jose)?
----------------------------
``python-jose`` 3.x does not support the ``EdDSA`` / Ed25519 algorithm —
``jose.constants.ALGORITHMS.SUPPORTED`` only lists HS/RS/ES/RSA-OAEP etc.
PyJWT 2.8+ supports EdDSA natively via the ``cryptography`` backend and its
``OKPAlgorithm.from_jwk`` helper reconstructs the public key from the
``kty=OKP`` / ``crv=Ed25519`` JWK entries that the Better Auth Worker serves.

The legacy HS256 self-signed tokens continue to live in
``app/services/auth_service.py`` (still on python-jose) until Phase 2 Group B
removes it.
"""
from __future__ import annotations

import json
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt.algorithms import OKPAlgorithm
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
    PyJWTError,
)

from app.core.config import settings
from app.services.jwks_client import get_key_for_kid


async def verify_jwt(token: str) -> dict[str, Any]:
    """Verify an EdDSA JWT against the JWKS from ``auth.bridgingchina.net``.

    Returns the decoded payload on success. Raises ``HTTPException(401)`` on
    any validation failure — callers in FastAPI dependencies should allow the
    exception to propagate.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
    except PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid token header"
        )

    kid = unverified_header.get("kid")
    alg = unverified_header.get("alg")
    if not kid or alg != "EdDSA":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid token header: kid/alg missing or unsupported",
        )

    jwk_dict = await get_key_for_kid(kid)
    if jwk_dict is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown key id")

    try:
        # Reconstruct a cryptography ``Ed25519PublicKey`` from the JWK entry.
        public_key = OKPAlgorithm().from_jwk(json.dumps(jwk_dict))
    except Exception:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Malformed JWKS key entry"
        )

    try:
        payload = jwt.decode(
            token,
            key=public_key,
            algorithms=["EdDSA"],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    except ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except InvalidIssuerError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token issuer")
    except InvalidAudienceError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid token audience"
        )
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Token invalid: {e}")

    return payload
