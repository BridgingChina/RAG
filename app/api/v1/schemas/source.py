"""Source management schemas."""
from datetime import datetime

from pydantic import BaseModel


class SourceListItem(BaseModel):
    id: int
    type: str
    title: str
    url: str | None
    chunk_count: int
    created_at: datetime


class SourceDetail(BaseModel):
    id: int
    type: str
    title: str
    url: str | None
    file_path: str | None
    accessed_at: datetime | None
    chunk_count: int
    created_at: datetime
