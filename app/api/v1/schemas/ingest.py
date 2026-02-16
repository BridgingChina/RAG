"""Ingest endpoint request/response schemas."""
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    """Request body for /api/v1/ingest endpoint."""
    content: str  # Markdown content
    source_type: str = "document"  # Source type (document, note, etc.)
    bridge_candidates: list[str] | None = None
    min_primary_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    enable_auto_bridge_detection: bool = True


BridgeBindingStatus: TypeAlias = Literal["none", "primary", "ambiguous"]


class IngestedChunkSummary(BaseModel):
    """Summary of an ingested chunk."""
    content_preview: str
    lvl1: str | None = None
    lvl2: str | None = None
    binding_status: BridgeBindingStatus
    primary_bridge_name: str | None = None
    secondary_bridge_names: list[str]


class IngestResponse(BaseModel):
    """Response body for /api/v1/ingest endpoint."""
    source_id: int
    title: str | None = None
    primary_bridge_names: list[str]
    ambiguous_chunk_count: int
    auto_created_bridges: list[str]
    chunk_count: int
    chunks: list[IngestedChunkSummary]
