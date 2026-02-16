"""Tests for auth-related models."""


def test_user_model_importable():
    from app.models import User
    assert User.__tablename__ == "users"


def test_audit_log_model_importable():
    from app.models import AuditLog
    assert AuditLog.__tablename__ == "audit_logs"
