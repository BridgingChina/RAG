"""Source management schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SourceListItem(BaseModel):
    id: UUID
    type: str
    title: str
    url: str | None
    chunk_count: int
    created_at: datetime


class SourceDetail(BaseModel):
    id: UUID
    type: str
    title: str
    url: str | None
    file_path: str | None
    accessed_at: datetime | None
    chunk_count: int
    created_at: datetime
