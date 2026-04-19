"""Tests for auth-related models.

Phase 2: ``User`` ORM table is gone (identity moved to auth.bridgingchina.net).
The AuditLog table stays, and ``CurrentUser`` is the JWT projection that
admin endpoints inject via ``get_current_user``.
"""


def test_audit_log_model_importable():
    from app.models import AuditLog
    assert AuditLog.__tablename__ == "audit_logs"


def test_audit_log_user_id_is_string_not_uuid():
    """Phase 2: audit_logs.user_id holds Better Auth base64url ids, not UUIDs."""
    from app.models import AuditLog
    from sqlalchemy import String
    assert isinstance(AuditLog.__table__.c.user_id.type, String)


def test_current_user_importable():
    from app.models.current_user import CurrentUser
    user = CurrentUser(id="abc", email="a@b", role="admin")
    assert user.id == "abc"
    assert user.role == "admin"
