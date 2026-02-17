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
