import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class IngestTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ingest_tasks"

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploading")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    r2_raw_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    r2_parsed_prefix: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    zhipu_task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True
    )
    parsed_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_ingest_tasks_status", "status"),
    )
