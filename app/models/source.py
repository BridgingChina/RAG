from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class Source(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sources"

    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    # i18n schema v16 (2026-05-08): English title for citation rendering
    # in en-US locale. nullable; populated by translation_review flow.
    title_en: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
