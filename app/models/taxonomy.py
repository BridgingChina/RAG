from typing import Optional

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin


class TaxonomyNode(Base, UUIDMixin):
    __tablename__ = "taxonomy_nodes"

    lvl1: Mapped[str] = mapped_column(String(100))
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # i18n (schema v12, 2026-04-21) — English display name for the current node's
    # level label (lvl1/lvl2/lvl3 depending on which column is non-NULL for the row).
    name_en: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        Index(
            "uq_taxonomy_nodes_path",
            "lvl1",
            text("COALESCE(lvl2, '')"),
            text("COALESCE(lvl3, '')"),
            unique=True,
        ),
    )
