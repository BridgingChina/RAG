"""Chunk management schemas."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class ChunkListItem(BaseModel):
    id: int
    content_preview: str
    bridge_id: int | None
    bridge_name: str | None
    lvl1: str | None
    lvl2: str | None
    binding_status: str
    source_id: int
    source_title: str | None
    created_at: datetime


class ChunkBridgeLinkDetail(BaseModel):
    id: int
    bridge_id: int
    bridge_name: str | None
    role: str
    confidence: float
    method: str


class ChunkDetail(BaseModel):
    id: int
    content: str
    contextual_text: str | None
    search_text: str | None
    section_title: str | None
    page_range: str | None
    lvl1: str | None
    lvl2: str | None
    lvl3: str | None
    bridge_id: int | None
    bridge_name: str | None
    binding_status: str
    source_id: int
    source_title: str | None
    created_at: datetime
    bridge_links: list[ChunkBridgeLinkDetail]


class ChunkUpdate(BaseModel):
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None
