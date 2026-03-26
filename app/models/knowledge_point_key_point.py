import uuid
from typing import Optional

from sqlalchemy import ARRAY, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class KnowledgePointKeyPoint(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "knowledge_point_key_points"

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    illustration_urls: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    related_term_ids: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )

    __table_args__ = (
        Index("ix_kpkp_kp", "knowledge_point_id"),
    )
