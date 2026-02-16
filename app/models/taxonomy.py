from typing import Optional

from sqlalchemy import Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaxonomyNode(Base):
    __tablename__ = "taxonomy_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    lvl1: Mapped[str] = mapped_column(String(100))
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Use COALESCE-based unique index so NULL columns are treated as ''
    # (plain UniqueConstraint doesn't prevent duplicates when columns are NULL)
    __table_args__ = (
        Index(
            "uq_taxonomy_nodes_path",
            "lvl1",
            text("COALESCE(lvl2, '')"),
            text("COALESCE(lvl3, '')"),
            unique=True,
        ),
    )
