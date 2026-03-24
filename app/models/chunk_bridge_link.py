import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, CreatedAtMixin


class ChunkBridgeLink(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "chunk_bridge_links"

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=False)
    bridge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bridges.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("ix_chunk_bridge_links_chunk_id", "chunk_id"),
        Index("ix_chunk_bridge_links_bridge_id", "bridge_id"),
        Index("ix_chunk_bridge_links_role_confidence", "role", "confidence"),
    )
