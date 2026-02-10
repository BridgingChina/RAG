"""API v1 request/response schemas."""
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


class AskContext(BaseModel):
    """Optional context for filtering retrieval."""
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    """Request body for /api/v1/ask endpoint."""
    question: str
    target_bridge_id: int | None = None
    context: AskContext | None = None


class CitationResponse(BaseModel):
    """Citation reference in response."""
    chunk_id: int
    source_title: str
    page_range: str | None


ConfidenceLevel: TypeAlias = Literal["high", "medium", "low"]


class ConfidenceResponse(BaseModel):
    """Confidence assessment for the answer."""
    level: ConfidenceLevel
    reason: str


class ChunkSummary(BaseModel):
    """Summary of a retrieved chunk."""
    chunk_id: int
    bridge_id: int | None = None
    bridge_name: str | None = None
    preview: str


class EvidenceGroupsResponse(BaseModel):
    """Evidence grouped by retrieval channel."""
    anchor: list[ChunkSummary]
    concept: list[ChunkSummary]
    analogy: list[ChunkSummary]


class AskResponse(BaseModel):
    """Response body for /api/v1/ask endpoint."""
    summary: str
    details: str
    analogy: str | None = None
    citations: list[CitationResponse]
    sources: list[str]
    confidence: ConfidenceResponse
    evidence_groups: EvidenceGroupsResponse | None = None
    degraded: list[str] | None = None


# Ingest schemas


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
