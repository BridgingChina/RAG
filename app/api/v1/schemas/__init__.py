"""API v1 schemas package - re-exports all schema types for backward compatibility."""

# Common schemas
from .common import PageParams, PaginatedResponse

# Ask schemas
from .ask import (
    AskContext,
    AskRequest,
    AskResponse,
    ChunkSummary,
    CitationResponse,
    ConfidenceLevel,
    ConfidenceResponse,
    EvidenceGroupsResponse,
)

# Ingest schemas
from .ingest import (
    BridgeBindingStatus,
    IngestRequest,
    IngestResponse,
    IngestedChunkSummary,
)

__all__ = [
    # Common
    "PageParams",
    "PaginatedResponse",
    # Ask
    "AskContext",
    "AskRequest",
    "AskResponse",
    "ChunkSummary",
    "CitationResponse",
    "ConfidenceLevel",
    "ConfidenceResponse",
    "EvidenceGroupsResponse",
    # Ingest
    "BridgeBindingStatus",
    "IngestRequest",
    "IngestResponse",
    "IngestedChunkSummary",
]
