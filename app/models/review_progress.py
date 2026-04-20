"""ReviewProgress model — user-scoped SM-2 style review state per flashcard.

``user_id`` is a logical FK to ``auth.user.id`` (Better Auth) — no hard FK
because that table lives in a different database (Cloudflare D1). Orphaned
rows are reaped by the reconcile cron (see ``services/reconcile_orphans.py``).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReviewProgress(Base):
    __tablename__ = "review_progress"

    user_id: Mapped[str] = mapped_column(String, nullable=False)
    flashcard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flashcards.id", ondelete="CASCADE"),
        nullable=False,
    )
    mastery: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    last_reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    next_review_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    ease_factor: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, server_default=text("2.5")
    )

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "flashcard_id", name="pk_review_progress"),
    )
