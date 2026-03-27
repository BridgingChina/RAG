import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Flashcard(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "flashcards"

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False
    )
    card_type: Mapped[str] = mapped_column(String(20), nullable=False)
    front_title: Mapped[str] = mapped_column(Text, nullable=False)
    front_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    back_answer: Mapped[str] = mapped_column(Text, nullable=False)
    back_key_features: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    back_example_bridge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bridges.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_flashcards_kp", "knowledge_point_id"),
    )
