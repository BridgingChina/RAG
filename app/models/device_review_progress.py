import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import REAL, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class DeviceReviewProgress(Base, UUIDMixin):
    __tablename__ = "device_review_progress"

    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    flashcard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flashcards.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastery: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'needs_review'")
    )
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interval: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    ease_factor: Mapped[float] = mapped_column(REAL, nullable=False, server_default=text("2.5"))

    __table_args__ = (
        UniqueConstraint("device_id", "flashcard_id", name="uq_device_review"),
        CheckConstraint("mastery IN ('mastered', 'needs_review')", name="ck_review_mastery"),
    )
