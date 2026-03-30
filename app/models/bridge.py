from typing import Optional

from sqlalchemy import Double, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class Bridge(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "bridges"

    name: Mapped[str] = mapped_column(String(255), unique=True)
    aliases: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    era: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    material: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    function: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Double, nullable=True)

    __table_args__ = (
        Index("ix_bridges_geo", "latitude", "longitude",
              postgresql_where=text("latitude IS NOT NULL")),
    )
