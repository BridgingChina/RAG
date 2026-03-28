import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class KnowledgePointBridge(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "knowledge_point_bridges"

    knowledge_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_points.id", ondelete="CASCADE"), nullable=False
    )
    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bridges.id", ondelete="CASCADE"), nullable=False
    )
    relevance_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("knowledge_point_id", "bridge_id", name="uq_kp_bridge"),
    )
