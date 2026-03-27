"""Knowledge point admin schemas."""
from uuid import UUID

from pydantic import BaseModel, Field


class KPCreate(BaseModel):
    taxonomy_node_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    aliases: str | None = None
    difficulty: str | None = None
    summary: str | None = None


class KPUpdate(BaseModel):
    taxonomy_node_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: str | None = None
    difficulty: str | None = None
    summary: str | None = None
    l2_content: dict | None = None


class KeyPointItem(BaseModel):
    id: UUID
    summary: str
    explanation: str | None
    order_index: int
    chunk_ids: list[str] = []


class KPDetail(BaseModel):
    id: UUID
    taxonomy_node_id: UUID | None
    name: str
    aliases: str | None
    difficulty: str | None
    summary: str | None
    l2_content: dict | None
    key_points: list[KeyPointItem] = []


class KPListItem(BaseModel):
    id: UUID
    name: str
    taxonomy_node_id: UUID | None
    difficulty: str | None
    summary: str | None
