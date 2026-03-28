"""API v1 schemas package - re-exports all schema types for backward compatibility."""

# Common schemas
from .common import PaginatedResponse

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
    BridgeMergePreview,
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
from .knowledge_point import (
    GenerateKeyPointsResponse,
    KPBridgeItem,
    KPBridgeReplaceItem,
    KPBridgeReplaceRequest,
    KPCreate,
    KPDetail,
    KPListItem,
    KPUpdate,
    KeyPointItem,
)

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

# Bridge image schemas
from .bridge_image import (
    BridgeImageResponse,
    ImageConfirmRequest,
    ImagePresignRequest,
    ImagePresignResponse,
    ImageReorderRequest,
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
    "BridgeMergePreview",
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
    "KPBridgeItem",
    "KPBridgeReplaceItem",
    "KPBridgeReplaceRequest",
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
    # Bridge image
    "BridgeImageResponse",
    "ImageConfirmRequest",
    "ImagePresignRequest",
    "ImagePresignResponse",
    "ImageReorderRequest",
    # Taxonomy
    "TaxonomyBatchUpdate",
    "TaxonomyBatchUpdateResult",
    "TaxonomyNodeCreate",
    "TaxonomyNodeDetail",
    "TaxonomyNodeUpdate",
    "TaxonomyTree",
    "TaxonomyTreeItem",
]
