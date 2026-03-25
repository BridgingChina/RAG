"""Tests for auth service — password hashing and JWT."""

import uuid

from app.services.auth_service import hash_password, verify_password, create_access_token, decode_access_token

_USER_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_hash_and_verify_password():
    hashed = hash_password("testpass123")
    assert hashed != "testpass123"
    assert verify_password("testpass123", hashed) is True
    assert verify_password("wrongpass", hashed) is False


def test_create_and_decode_token():
    token = create_access_token(user_id=_USER_UUID, username="admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == str(_USER_UUID)
    assert payload["username"] == "admin"


def test_decode_invalid_token():
    payload = decode_access_token("invalid.token.here")
    assert payload is None
