import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func, text as sql_text
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import EMBEDDING_DIM
from app.models.base import Base, UUIDMixin, CreatedAtMixin


class Chunk(Base, UUIDMixin, CreatedAtMixin):
    __tablename__ = "chunks"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"))
    content: Mapped[str] = mapped_column(Text)
    section_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lvl1: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lvl3: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bridge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bridges.id"), nullable=True
    )
    bridge_binding_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=sql_text("'none'")
    )
    page_range: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    contextual_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    search_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tsv: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)
    needs_reindex: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_chunks_taxonomy", "lvl1", "lvl2", "lvl3"),
        Index("ix_chunks_bridge", "bridge_id"),
        Index("ix_chunks_source", "source_id"),
        Index("ix_chunks_binding_status", "bridge_binding_status"),
        Index(
            "ix_chunks_needs_reindex", "source_id",
            postgresql_where=sql_text("needs_reindex = true"),
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
