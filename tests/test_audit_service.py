"""Tests for audit service."""

from app.services.audit_service import AuditService


def test_audit_service_importable():
    assert callable(AuditService.log)


def test_audit_log_action_constants():
    """Verify action constants are defined."""
    assert AuditService.LOGIN == "login"
    assert AuditService.LOGIN_FAILURE == "login_failure"
    assert AuditService.CREATE == "create"
    assert AuditService.UPDATE == "update"
    assert AuditService.DELETE == "delete"
    assert AuditService.MERGE == "merge"
    assert AuditService.INGEST == "ingest"
