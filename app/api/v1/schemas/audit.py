"""Audit log schemas.

Phase 2: ``user_id`` is a Better Auth user id string (not a UUID); the
historical JOIN to ``users.username`` is gone because that table lives in
the auth Worker now. Clients that need the username should hit
``/api/v1/auth/me`` or the auth Worker directly.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: UUID
    user_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict | None
    ip_address: str | None
    created_at: datetime
