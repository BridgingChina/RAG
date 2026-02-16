from typing import Optional

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TaxonomyNode(Base):
    __tablename__ = "taxonomy_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    lvl1: Mapped[str] = mapped_column(String(100))
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("lvl1", "lvl2", "lvl3", name="uq_taxonomy_nodes_path"),
    )
