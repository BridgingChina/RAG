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
    geocode_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # i18n (schema v12, 2026-04-21) — English-translated display fields. Populated
    # through the translation_reviews審校 workflow; NULL means C-end falls back to
    # the Chinese value with response meta.translation_fallback=true.
    name_en: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_bridges_geo", "latitude", "longitude",
              postgresql_where=text("latitude IS NOT NULL AND longitude IS NOT NULL")),
    )
