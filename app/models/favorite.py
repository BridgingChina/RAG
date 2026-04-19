"""Favorite model — user-scoped bookmark for bridge / knowledge_point / flashcard."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class Favorite(Base, UUIDMixin):
    __tablename__ = "favorites"

    user_id: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "target_id", "target_type", name="uq_favorite"),
        Index("idx_favorites_user", "user_id"),
        CheckConstraint(
            "target_type IN ('bridge', 'knowledge_point', 'flashcard')",
            name="ck_favorite_target_type",
        ),
    )
