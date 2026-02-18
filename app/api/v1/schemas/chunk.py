"""Chunk management schemas."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, field_validator


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
    needs_reindex: bool


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
    needs_reindex: bool


class BridgeLinkInput(BaseModel):
    bridge_id: int
    role: Literal["primary", "secondary", "candidate"]
    confidence: float = 1.0
    method: Literal["hint", "rule", "llm", "manual"] = "manual"


class ChunkUpdate(BaseModel):
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None
    content: str | None = None
    section_title: str | None = None
    bridge_links: list[BridgeLinkInput] | None = None

    @field_validator("lvl1", "lvl2", "lvl3", mode="before")
    @classmethod
    def normalize_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip() if isinstance(v, str) else v
            if isinstance(v, str) and not v:
                return None
        return v


class ChunkSplitRequest(BaseModel):
    position: int


class ChunkSplitResponse(BaseModel):
    chunks: list[ChunkDetail]


class ChunkMergeRequest(BaseModel):
    chunk_ids: list[int]


class ChunkBatchUpdate(BaseModel):
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None
    bridge_id: int | None = None
    binding_status: Literal["none", "primary", "ambiguous"] | None = None

    @field_validator("lvl1", "lvl2", "lvl3", mode="before")
    @classmethod
    def normalize_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip() if isinstance(v, str) else v
            if isinstance(v, str) and not v:
                return None
        return v


class ChunkBatchRequest(BaseModel):
    chunk_ids: list[int]
    action: Literal["update", "delete"]
    updates: ChunkBatchUpdate | None = None


class ReindexResponse(BaseModel):
    source_id: int
    chunks_reindexed: int
    chunks_failed: list[int]
