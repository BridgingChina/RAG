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

# Chunk schemas
from .chunk import (
    ChunkBridgeLinkDetail,
    ChunkDetail,
    ChunkListItem,
    ChunkUpdate,
)

# Ingest schemas
from .ingest import (
    BridgeBindingStatus,
    IngestRequest,
    IngestResponse,
    IngestedChunkSummary,
)

# Stats schemas
from .stats import (
    BindingDistribution,
    DashboardStats,
    Lvl1Distribution,
    RecentIngest,
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
    # Chunk
    "ChunkBridgeLinkDetail",
    "ChunkDetail",
    "ChunkListItem",
    "ChunkUpdate",
    # Ingest
    "BridgeBindingStatus",
    "IngestRequest",
    "IngestResponse",
    "IngestedChunkSummary",
    # Stats
    "BindingDistribution",
    "DashboardStats",
    "Lvl1Distribution",
    "RecentIngest",
]
