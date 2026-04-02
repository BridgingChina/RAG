"""Audit log model for tracking write operations."""

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, CreatedAtMixin


class AuditLog(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "audit_logs"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action_resource", "action", "resource_type"),
    )
