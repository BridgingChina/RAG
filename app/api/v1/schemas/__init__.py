"""API v1 schemas package - re-exports all schema types for backward compatibility."""

# Common schemas
from .common import PageParams, PaginatedResponse

# Audit schemas
from .audit import AuditLogItem

# Auth schemas
from .auth import ChangePasswordRequest, LoginRequest, LoginResponse, UserInfo

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
    BridgeLinkInput,
    ChunkBatchRequest,
    ChunkBatchUpdate,
    ChunkBridgeLinkDetail,
    ChunkDetail,
    ChunkListItem,
    ChunkMergeRequest,
    ChunkSplitRequest,
    ChunkSplitResponse,
    ChunkUpdate,
    ReindexResponse,
)

# Knowledge point schemas
from .knowledge_point import KPCreate, KPDetail, KPListItem, KPUpdate

# Ingest schemas
from .ingest import (
    BridgeBindingStatus,
    IngestRequest,
    IngestResponse,
    IngestedChunkSummary,
)

# IngestTask schemas
from .ingest_task import (
    IngestTaskCreate,
    IngestTaskDetail,
    IngestTaskListItem,
    PresignRequest,
    PresignResponse,
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
    # Audit
    "AuditLogItem",
    # Common
    "PageParams",
    "PaginatedResponse",
    # Auth
    "ChangePasswordRequest",
    "LoginRequest",
    "LoginResponse",
    "UserInfo",
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
    "BridgeLinkInput",
    "ChunkBatchRequest",
    "ChunkBatchUpdate",
    "ChunkBridgeLinkDetail",
    "ChunkDetail",
    "ChunkListItem",
    "ChunkMergeRequest",
    "ChunkSplitRequest",
    "ChunkSplitResponse",
    "ChunkUpdate",
    "ReindexResponse",
    # Knowledge point
    "KPCreate",
    "KPDetail",
    "KPListItem",
    "KPUpdate",
    # Ingest
    "BridgeBindingStatus",
    "IngestRequest",
    "IngestResponse",
    "IngestedChunkSummary",
    # IngestTask
    "IngestTaskCreate",
    "IngestTaskDetail",
    "IngestTaskListItem",
    "PresignRequest",
    "PresignResponse",
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
