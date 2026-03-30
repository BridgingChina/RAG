import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAtMixin, UUIDMixin


class BridgeImage(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "bridge_images"

    bridge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bridges.id", ondelete="CASCADE"), nullable=False
    )
    r2_key: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (
        Index("ix_bridge_images_bridge_id", "bridge_id"),
    )
