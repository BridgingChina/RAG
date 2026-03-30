"""Tests for auth service — password hashing and JWT."""

import uuid
from datetime import datetime, timedelta, timezone

from app.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    is_token_valid_for_user,
    verify_password,
)

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


def test_token_contains_iat_claim():
    token = create_access_token(user_id=_USER_UUID, username="admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert "iat" in payload
    # iat should be a recent Unix timestamp
    iat = payload["iat"]
    now_ts = datetime.now(timezone.utc).timestamp()
    assert abs(now_ts - iat) < 10  # within 10 seconds


def test_decode_invalid_token():
    payload = decode_access_token("invalid.token.here")
    assert payload is None


def test_is_token_valid_no_password_change():
    """Token is valid when user has never changed password."""
    payload = {"iat": datetime.now(timezone.utc).timestamp()}
    assert is_token_valid_for_user(payload, password_changed_at=None) is True


def test_is_token_valid_token_after_password_change():
    """Token issued after password change is valid."""
    changed_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    iat = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc).timestamp()
    payload = {"iat": iat}
    assert is_token_valid_for_user(payload, password_changed_at=changed_at) is True


def test_is_token_invalid_token_before_password_change():
    """Token issued before password change is invalid."""
    changed_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    iat = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc).timestamp()
    payload = {"iat": iat}
    assert is_token_valid_for_user(payload, password_changed_at=changed_at) is False


def test_is_token_invalid_no_iat_with_password_change():
    """Token without iat is invalid if password was ever changed."""
    changed_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    payload = {}
    assert is_token_valid_for_user(payload, password_changed_at=changed_at) is False
