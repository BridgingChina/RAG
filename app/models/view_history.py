"""ViewHistory model — user-scoped bridge / knowledge_point view log."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class ViewHistory(Base, UUIDMixin):
    __tablename__ = "view_history"

    user_id: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_view_history_user_time", "user_id", "viewed_at"),
        CheckConstraint(
            "target_type IN ('bridge', 'knowledge_point')",
            name="ck_view_history_target_type",
        ),
    )
