"""Smoke tests that exercise the JWT dependencies through a real FastAPI
TestClient.

Purpose: catch FastAPI-layer wiring issues (dependency instantiation, OpenAPI
schema registration, ``HTTPBearer`` auto_error behaviour) that the per-function
async unit tests in ``test_dependencies.py`` cannot detect.

Fixtures are duplicated (not extracted to conftest) because doing so would
require touching every test in ``test_dependencies.py`` / ``test_jwt_verifier.py``
— option (b) from the plan.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.public.v1.dependencies import get_optional_user, require_user
from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.models.current_user import CurrentUser
from app.services import jwt_verifier


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


@pytest.fixture
def ed25519_setup(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Generate an ephemeral Ed25519 keypair and patch
    ``jwt_verifier.get_key_for_kid`` to hand back the public half as a JWK."""
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    kid = "smoke-test-kid"
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64url(pub_raw),
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
    sub: str = "smoke-user",
    email: str = "smoke@example.com",
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


@pytest.fixture
def admin_token(ed25519_setup: dict[str, Any]) -> str:
    return _make_token(ed25519_setup, role="admin", sub="admin-smoke")


@pytest.fixture
def user_token(ed25519_setup: dict[str, Any]) -> str:
    return _make_token(ed25519_setup, role="user", sub="user-smoke")


@pytest.fixture
def app_with_routes(ed25519_setup: dict[str, Any]) -> FastAPI:
    """Minimal FastAPI app mounting one route per dependency variant."""
    app = FastAPI()

    @app.get("/admin/me")
    async def admin_me(user: CurrentUser = Depends(get_current_user)) -> dict:
        return {"id": user.id, "role": user.role}

    @app.get("/public/maybe")
    async def public_maybe(
        user: CurrentUser | None = Depends(get_optional_user),
    ) -> dict:
        return {
            "anonymous": user is None,
            "id": user.id if user is not None else None,
        }

    @app.get("/public/required")
    async def public_required(user: CurrentUser = Depends(require_user)) -> dict:
        return {"id": user.id}

    return app


# ---------------------------------------------------------------------------
# admin route — backed by HTTPBearer(auto_error=True)
# ---------------------------------------------------------------------------


def test_admin_route_rejects_no_auth(app_with_routes: FastAPI) -> None:
    client = TestClient(app_with_routes)
    resp = client.get("/admin/me")
    # HTTPBearer(auto_error=True) in current FastAPI returns 401 for missing
    # credentials (historically 403; changed to 401 to match RFC 7235). We
    # verify against whichever the installed FastAPI chooses rather than
    # hard-coding one value — either surfaces the "unauthenticated" intent.
    assert resp.status_code in (401, 403)


def test_admin_route_rejects_garbage_token(app_with_routes: FastAPI) -> None:
    client = TestClient(app_with_routes)
    resp = client.get("/admin/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_admin_route_accepts_valid_admin_token(
    app_with_routes: FastAPI, admin_token: str
) -> None:
    client = TestClient(app_with_routes)
    resp = client.get(
        "/admin/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["id"] == "admin-smoke"


def test_admin_route_rejects_non_admin_user_token(
    app_with_routes: FastAPI, user_token: str
) -> None:
    client = TestClient(app_with_routes)
    resp = client.get(
        "/admin/me", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# public /maybe — optional auth
# ---------------------------------------------------------------------------


def test_public_maybe_anonymous_without_auth(app_with_routes: FastAPI) -> None:
    client = TestClient(app_with_routes)
    resp = client.get("/public/maybe")
    assert resp.status_code == 200
    assert resp.json() == {"anonymous": True, "id": None}


def test_public_maybe_authenticated_with_valid_token(
    app_with_routes: FastAPI, user_token: str
) -> None:
    client = TestClient(app_with_routes)
    resp = client.get(
        "/public/maybe", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["anonymous"] is False
    assert body["id"] == "user-smoke"


def test_public_maybe_degrades_to_anonymous_on_garbage(
    app_with_routes: FastAPI,
) -> None:
    client = TestClient(app_with_routes)
    resp = client.get(
        "/public/maybe", headers={"Authorization": "Bearer garbage"}
    )
    assert resp.status_code == 200
    assert resp.json()["anonymous"] is True


# ---------------------------------------------------------------------------
# public /required — 401 when missing
# ---------------------------------------------------------------------------


def test_public_required_401_without_auth(app_with_routes: FastAPI) -> None:
    """``require_user`` chains off ``get_optional_user`` which uses
    ``HTTPBearer(auto_error=False)``, so missing credentials reach the
    wrapper and surface as HTTPException(401) — NOT 403."""
    client = TestClient(app_with_routes)
    resp = client.get("/public/required")
    assert resp.status_code == 401


def test_public_required_accepts_valid_token(
    app_with_routes: FastAPI, user_token: str
) -> None:
    client = TestClient(app_with_routes)
    resp = client.get(
        "/public/required", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == "user-smoke"
