"""Knowledge point admin schemas."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KPCreate(BaseModel):
    taxonomy_node_id: UUID | None = None
    lvl1: str | None = Field(default=None, max_length=100)
    lvl2: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    aliases: str | None = None
    difficulty: str | None = None
    summary: str | None = None


class KPUpdate(BaseModel):
    taxonomy_node_id: UUID | None = None
    lvl1: str | None = Field(default=None, max_length=100)
    lvl2: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: str | None = None
    difficulty: str | None = None
    summary: str | None = None
    l2_content: dict | None = None


class AutoAssociateResult(BaseModel):
    candidate_count: int
    matched_chunk_ids: list[UUID]


class KeyPointItem(BaseModel):
    id: UUID
    summary: str
    explanation: str | None
    order_index: int
    chunk_ids: list[str] = []


class KPDetail(BaseModel):
    id: UUID
    taxonomy_node_id: UUID | None
    lvl1: str | None = None
    lvl2: str | None = None
    name: str
    aliases: str | None
    difficulty: str | None
    summary: str | None
    l2_content: dict | None
    key_points: list[KeyPointItem] = []


class GenerateKeyPointsResponse(BaseModel):
    generated: int
    key_points: list[KeyPointItem] = []


class KPListItem(BaseModel):
    id: UUID
    name: str
    taxonomy_node_id: UUID | None
    lvl1: str | None = None
    lvl2: str | None = None
    difficulty: str | None
    summary: str | None


class KPBridgeItem(BaseModel):
    id: UUID
    bridge_id: UUID
    bridge_name: str
    relevance_note: str | None
    order_index: int
    model_config = ConfigDict(from_attributes=True)


class KPBridgeReplaceItem(BaseModel):
    bridge_id: UUID
    relevance_note: str | None = None
    order_index: int = 0


class KPBridgeReplaceRequest(BaseModel):
    items: list[KPBridgeReplaceItem]
