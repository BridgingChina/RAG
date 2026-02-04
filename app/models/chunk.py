from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Chunk(Base, TimestampMixin):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    content: Mapped[str] = mapped_column(Text)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lvl1: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bridges.id"), nullable=True
    )
    page_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(2048))
    contextual_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tsv: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("ix_chunks_taxonomy", "lvl1", "lvl2", "lvl3"),
        Index("ix_chunks_bridge", "bridge_id"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        # pgvector IVFFLAT index for cosine distance (<=>).
        # Note: IVFFLAT supports dimensions > 2000 (HNSW limit is 2000).
        Index(
            "ix_chunks_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
