from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ChunkBridgeLink(Base, TimestampMixin):
    __tablename__ = "chunk_bridge_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id"), nullable=False)
    bridge_id: Mapped[int] = mapped_column(ForeignKey("bridges.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("ix_chunk_bridge_links_chunk_id", "chunk_id"),
        Index("ix_chunk_bridge_links_bridge_id", "bridge_id"),
        Index("ix_chunk_bridge_links_role_confidence", "role", "confidence"),
    )
