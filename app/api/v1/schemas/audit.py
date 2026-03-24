"""Audit log schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: UUID
    user_id: UUID | None
    username: str | None
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    created_at: datetime
