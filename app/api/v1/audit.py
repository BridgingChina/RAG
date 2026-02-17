"""Audit log API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.v1.schemas.audit import AuditLogItem
from app.api.v1.schemas.common import PaginatedResponse
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=PaginatedResponse[AuditLogItem])
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    db: Session = Depends(get_db),
) -> PaginatedResponse[AuditLogItem]:
    """List audit logs with optional filters."""
    query = db.query(
        AuditLog.id,
        AuditLog.user_id,
        User.username,
        AuditLog.action,
        AuditLog.resource_type,
        AuditLog.resource_id,
        AuditLog.detail,
        AuditLog.ip_address,
        AuditLog.created_at,
    ).outerjoin(User, AuditLog.user_id == User.id)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if resource_type is not None:
        query = query.filter(AuditLog.resource_type == resource_type)
    if start is not None:
        query = query.filter(AuditLog.created_at >= start)
    if end is not None:
        query = query.filter(AuditLog.created_at <= end)

    total = query.count()
    offset = (page - 1) * page_size
    results = query.order_by(desc(AuditLog.created_at)).offset(offset).limit(page_size).all()

    items = [
        AuditLogItem(
            id=row.id,
            user_id=row.user_id,
            username=row.username,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            detail=row.detail,
            ip_address=row.ip_address,
            created_at=row.created_at,
        )
        for row in results
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )
