"""Ask endpoint request/response schemas."""
from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel


class AskContext(BaseModel):
    """Optional context for filtering retrieval."""
    bridge_id: UUID | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    """Request body for /api/v1/ask endpoint."""
    question: str
    target_bridge_id: UUID | None = None
    context: AskContext | None = None
    debug: bool = False


class CitationResponse(BaseModel):
    """Citation reference in response."""
    chunk_id: UUID
    source_title: str
    page_range: str | None


ConfidenceLevel: TypeAlias = Literal["high", "medium", "low"]


class ConfidenceResponse(BaseModel):
    """Confidence assessment for the answer."""
    level: ConfidenceLevel
    reason: str


class ChunkSummary(BaseModel):
    """Summary of a retrieved chunk."""
    chunk_id: UUID
    bridge_id: UUID | None = None
    bridge_name: str | None = None
    preview: str


class EvidenceGroupsResponse(BaseModel):
    """Evidence grouped by retrieval channel."""
    anchor: list[ChunkSummary]
    concept: list[ChunkSummary]
    analogy: list[ChunkSummary]


class ChannelDebugResponse(BaseModel):
    """Debug info for a single retrieval channel."""
    channel: str
    filter_desc: str
    vec_ids: list[UUID]
    fts_ids: list[UUID]
    rrf_scores: list[list]  # [[chunk_id, score], ...] — mixed UUID + float
    final_ids: list[UUID]


class DebugResponse(BaseModel):
    """Full debug info for a retrieval request."""
    facet: dict | None = None
    channels: list[ChannelDebugResponse] = []
    timings: dict[str, float] = {}


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
    debug: DebugResponse | None = None
