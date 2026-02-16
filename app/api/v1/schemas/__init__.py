"""API v1 schemas package - re-exports all schema types for backward compatibility."""

# Common schemas
from .common import PageParams, PaginatedResponse

# Ask schemas
from .ask import (
    AskContext,
    AskRequest,
    AskResponse,
    ChannelDebugResponse,
    ChunkSummary,
    CitationResponse,
    ConfidenceLevel,
    ConfidenceResponse,
    DebugResponse,
    EvidenceGroupsResponse,
)

# Bridge schemas
from .bridge import (
    BridgeCreate,
    BridgeDetail,
    BridgeListItem,
    BridgeMergeRequest,
    BridgeUpdate,
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

# Source schemas
from .source import SourceDetail, SourceListItem

# System schemas
from .system import SystemStatus

# Stats schemas
from .stats import (
    BindingDistribution,
    DashboardStats,
    Lvl1Distribution,
    RecentIngest,
)

# Taxonomy schemas
from .taxonomy import (
    TaxonomyBatchUpdate,
    TaxonomyBatchUpdateResult,
    TaxonomyNodeCreate,
    TaxonomyNodeDetail,
    TaxonomyNodeUpdate,
    TaxonomyTree,
    TaxonomyTreeItem,
)

__all__ = [
    # Common
    "PageParams",
    "PaginatedResponse",
    # Ask
    "AskContext",
    "AskRequest",
    "AskResponse",
    "ChannelDebugResponse",
    "ChunkSummary",
    "CitationResponse",
    "ConfidenceLevel",
    "ConfidenceResponse",
    "DebugResponse",
    "EvidenceGroupsResponse",
    # Bridge
    "BridgeCreate",
    "BridgeDetail",
    "BridgeListItem",
    "BridgeMergeRequest",
    "BridgeUpdate",
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
    # Source
    "SourceDetail",
    "SourceListItem",
    # System
    "SystemStatus",
    # Stats
    "BindingDistribution",
    "DashboardStats",
    "Lvl1Distribution",
    "RecentIngest",
    # Taxonomy
    "TaxonomyBatchUpdate",
    "TaxonomyBatchUpdateResult",
    "TaxonomyNodeCreate",
    "TaxonomyNodeDetail",
    "TaxonomyNodeUpdate",
    "TaxonomyTree",
    "TaxonomyTreeItem",
]
