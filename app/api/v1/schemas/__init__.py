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

# Bridge schemas
from .bridge import (
    BridgeCreate,
    BridgeDetail,
    BridgeListItem,
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
    "ChunkSummary",
    "CitationResponse",
    "ConfidenceLevel",
    "ConfidenceResponse",
    "EvidenceGroupsResponse",
    # Bridge
    "BridgeCreate",
    "BridgeDetail",
    "BridgeListItem",
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
