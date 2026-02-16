"""Bridge management schemas."""
from datetime import datetime
from pydantic import BaseModel


class BridgeListItem(BaseModel):
    id: int
    name: str
    aliases: str | None
    bridge_type: str | None
    material: str | None
    era: str | None
    location: str | None
    chunk_count: int
    created_at: datetime


class BridgeDetail(BaseModel):
    id: int
    name: str
    aliases: str | None
    bridge_type: str | None
    material: str | None
    era: str | None
    location: str | None
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
    location: str | None = None
    function: str | None = None
    summary: str | None = None


class BridgeUpdate(BaseModel):
    name: str | None = None
    aliases: str | None = None
    bridge_type: str | None = None
    material: str | None = None
    era: str | None = None
    location: str | None = None
    function: str | None = None
    summary: str | None = None


class BridgeMergeRequest(BaseModel):
    source_bridge_id: int
