"""Bridge management schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BridgeListItem(BaseModel):
    id: UUID
    name: str
    aliases: str | None
    bridge_type: str | None
    material: str | None
    era: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    chunk_count: int
    created_at: datetime


class BridgeDetail(BaseModel):
    id: UUID
    name: str
    aliases: str | None
    bridge_type: str | None
    material: str | None
    era: str | None
    region: str | None
    latitude: float | None
    longitude: float | None
    function: str | None
    summary: str | None
    chunk_count: int
    created_at: datetime


class BridgeCreate(BaseModel):
    name: str
    aliases: str | None = None
    bridge_type: str | None = None
    material: str | None = None
    era: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    function: str | None = None
    summary: str | None = None


class BridgeUpdate(BaseModel):
    name: str | None = None
    aliases: str | None = None
    bridge_type: str | None = None
    material: str | None = None
    era: str | None = None
    region: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    function: str | None = None
    summary: str | None = None


class BridgeMergeRequest(BaseModel):
    source_bridge_id: UUID


class BridgeMergePreview(BaseModel):
    source_bridge_id: UUID
    source_bridge_name: str
    target_bridge_id: UUID
    target_bridge_name: str
    chunks_to_move: int
    links_to_move: int
    aliases_to_add: list[str]
