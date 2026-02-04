from pydantic import BaseModel


class AskContext(BaseModel):
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    question: str
    target_bridge_id: int | None = None
    context: AskContext | None = None


class CitationResponse(BaseModel):
    chunk_id: int
    source_title: str
    page_range: str | None


class AskResponse(BaseModel):
    summary: str
    details: str
    citations: list[CitationResponse]
    sources: list[str]


class ConfidenceResponse(BaseModel):
    level: str  # "high" | "medium" | "low"
    reason: str


class ChunkSummary(BaseModel):
    chunk_id: int
    bridge_id: int | None = None
    bridge_name: str | None = None
    preview: str


class EvidenceGroupsResponse(BaseModel):
    anchor: list[ChunkSummary]
    concept: list[ChunkSummary]
    analogy: list[ChunkSummary]


class AskResponseV2(BaseModel):
    summary: str
    details: str
    analogy: str | None = None
    citations: list[CitationResponse]
    sources: list[str]
    confidence: ConfidenceResponse
    evidence_groups: EvidenceGroupsResponse | None = None
    degraded: bool | None = None
