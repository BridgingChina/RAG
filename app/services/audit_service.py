"""Audit logging service for tracking write operations."""

import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    # Action constants
    LOGIN = "login"
    LOGIN_FAILURE = "login_failure"
    CHANGE_PASSWORD = "change_password"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"
    INGEST = "ingest"
    BATCH_UPDATE = "batch_update"
    RETRY = "retry_ingest"
    INGEST_PARSE_START = "ingest_parse_start"
    INGEST_PARSE_DONE = "ingest_parse_done"
    INGEST_INDEX_DONE = "ingest_index_done"
    INGEST_FAILED = "ingest_failed"

    @staticmethod
    def log(
        db: Session,
        *,
        action: str,
        resource_type: str,
        user_id: uuid.UUID | None = None,
        resource_id: str | None = None,
        detail: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            ip_address=ip_address,
        )
        db.add(entry)
        db.flush()
