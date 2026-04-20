import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class KnowledgePoint(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "knowledge_points"

    taxonomy_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("taxonomy_nodes.id"), nullable=True
    )
    lvl1: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    l2_content: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # i18n (schema v12, 2026-04-21)
    name_en: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    summary_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_kp_taxonomy", "taxonomy_node_id"),
        Index("ix_kp_lvl1_lvl2", "lvl1", "lvl2"),
    )
