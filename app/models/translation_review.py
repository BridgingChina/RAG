"""TranslationReview model —审校状态机 for i18n Phase 3.

Schema v12 introduced a single审校 table that serves as the write-path and state
machine for每一条 *_en business-table column. Every (table_name, row_id,
field_name) triple is unique; status transitions are:

    pending_ai -> ai_generated -> human_reviewed
                               -> rejected

On ``approve`` the service writes ``reviewed_translation`` back into the business
table in the same transaction and flips status to ``human_reviewed``.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


# Valid status values (enforced in application code — no DB CHECK constraint so
# future values can be added without a migration).
TRANSLATION_STATUS_PENDING_AI = "pending_ai"
TRANSLATION_STATUS_AI_GENERATED = "ai_generated"
TRANSLATION_STATUS_HUMAN_REVIEWED = "human_reviewed"
TRANSLATION_STATUS_REJECTED = "rejected"

VALID_TRANSLATION_STATUSES: set[str] = {
    TRANSLATION_STATUS_PENDING_AI,
    TRANSLATION_STATUS_AI_GENERATED,
    TRANSLATION_STATUS_HUMAN_REVIEWED,
    TRANSLATION_STATUS_REJECTED,
}


class TranslationReview(Base, UUIDMixin):
    __tablename__ = "translation_reviews"

    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    ai_translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_translation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TRANSLATION_STATUS_PENDING_AI,
    )
    # Phase 2 identity: Better Auth ids are base64url strings, not UUIDs, so we
    # accept TEXT here like audit_logs.user_id. No FK — the users table has
    # moved to the auth Worker's D1.
    reviewed_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "table_name", "row_id", "field_name", name="uq_translation",
        ),
        Index("idx_translation_reviews_status", "status"),
        Index("idx_translation_reviews_table_field", "table_name", "field_name"),
    )
