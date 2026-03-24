from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, CreatedAtMixin


class Source(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "sources"

    type: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
