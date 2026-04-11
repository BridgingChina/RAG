"""Schemas for ingest task endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PresignRequest(BaseModel):
    file_name: str
    file_type: str  # "pdf" | "md"
    file_size: int  # bytes
    content_type: str  # MIME type


class PresignResponse(BaseModel):
    upload_url: str
    r2_key: str


class IngestTaskCreate(BaseModel):
    r2_key: str


class IngestTaskDetail(BaseModel):
    id: UUID
    status: str
    file_name: str
    file_type: str
    file_size: int | None
    source_id: UUID | None
    chunk_count: int | None
    image_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestTaskListItem(IngestTaskDetail):
    pass


class BatchDeleteRequest(BaseModel):
    task_ids: list[UUID]


class BatchDeleteFailure(BaseModel):
    task_id: UUID
    reason: str


class BatchDeleteResponse(BaseModel):
    deleted: list[UUID]
    skipped: list[UUID]
    failed: list[BatchDeleteFailure] = []


class DownloadUrlResponse(BaseModel):
    url: str
