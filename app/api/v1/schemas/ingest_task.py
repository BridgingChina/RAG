"""Schemas for ingest task endpoints."""
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
    file_name: str
    file_type: str
    file_size: int
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
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class IngestTaskListItem(BaseModel):
    id: UUID
    status: str
    file_name: str
    file_type: str
    file_size: int | None
    source_id: UUID | None
    chunk_count: int | None
    image_count: int
    error_message: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class BatchDeleteRequest(BaseModel):
    task_ids: list[UUID]


class BatchDeleteResponse(BaseModel):
    deleted: list[UUID]
    skipped: list[UUID]


class DownloadUrlResponse(BaseModel):
    url: str
