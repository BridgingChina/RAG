// --- Ask ---

export interface AskRequest {
  question: string
  target_bridge_id?: number | null
}

export interface CitationResponse {
  chunk_id: number
  source_title: string
  page_range: string | null
}

export interface ConfidenceResponse {
  level: "high" | "medium" | "low"
  reason: string
}

export interface ChunkSummary {
  chunk_id: number
  bridge_id: number | null
  bridge_name: string | null
  preview: string
}

export interface EvidenceGroupsResponse {
  anchor: ChunkSummary[]
  concept: ChunkSummary[]
  analogy: ChunkSummary[]
}

export interface AskResponse {
  summary: string
  details: string
  analogy: string | null
  citations: CitationResponse[]
  sources: string[]
  confidence: ConfidenceResponse
  evidence_groups: EvidenceGroupsResponse | null
  degraded: string[] | null
  debug?: DebugInfo | null
}

// --- Ingest ---

export interface IngestRequest {
  content: string
  source_type: string
  bridge_candidates?: string[] | null
  min_primary_confidence?: number
  enable_auto_bridge_detection?: boolean
}

export interface IngestedChunkSummary {
  content_preview: string
  lvl1: string | null
  lvl2: string | null
  binding_status: "none" | "primary" | "ambiguous"
  primary_bridge_name: string | null
  secondary_bridge_names: string[]
}

export interface IngestResponse {
  source_id: number
  title: string | null
  primary_bridge_names: string[]
  ambiguous_chunk_count: number
  auto_created_bridges: string[]
  chunk_count: number
  chunks: IngestedChunkSummary[]
}

// --- Pagination ---

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// --- Dashboard ---

export interface BindingDistribution {
  primary: number
  ambiguous: number
  none: number
}

export interface Lvl1Distribution {
  label: string
  count: number
}

export interface RecentIngest {
  source_id: number
  title: string | null
  chunk_count: number
  created_at: string
}

export interface DashboardStats {
  chunk_count: number
  bridge_count: number
  source_count: number
  ambiguous_ratio: number
  binding_distribution: BindingDistribution
  lvl1_distribution: Lvl1Distribution[]
  recent_ingests: RecentIngest[]
}

// --- Chunks ---

export interface ChunkListItem {
  id: number
  content_preview: string
  bridge_id: number | null
  bridge_name: string | null
  lvl1: string | null
  lvl2: string | null
  binding_status: string
  source_id: number
  source_title: string | null
  created_at: string
}

export interface ChunkBridgeLinkDetail {
  id: number
  bridge_id: number
  bridge_name: string | null
  role: string
  confidence: number
  method: string
}

export interface ChunkDetail {
  id: number
  content: string
  contextual_text: string | null
  search_text: string | null
  section_title: string | null
  page_range: string | null
  lvl1: string | null
  lvl2: string | null
  lvl3: string | null
  bridge_id: number | null
  bridge_name: string | null
  binding_status: string
  source_id: number
  source_title: string | null
  created_at: string
  bridge_links: ChunkBridgeLinkDetail[]
}

export interface ChunkUpdateRequest {
  lvl1?: string | null
  lvl2?: string | null
  lvl3?: string | null
  bridge_id?: number | null
  binding_status?: "none" | "primary" | "ambiguous"
}

// --- Bridges ---

export interface BridgeListItem {
  id: number
  name: string
  aliases: string | null
  bridge_type: string | null
  material: string | null
  era: string | null
  location: string | null
  chunk_count: number
  created_at: string
}

export interface BridgeDetail {
  id: number
  name: string
  aliases: string | null
  bridge_type: string | null
  material: string | null
  era: string | null
  location: string | null
  function: string | null
  summary: string | null
  chunk_count: number
  created_at: string
}

export interface BridgeCreateRequest {
  name: string
  aliases?: string | null
  bridge_type?: string | null
  material?: string | null
  era?: string | null
  location?: string | null
  function?: string | null
  summary?: string | null
}

export interface BridgeUpdateRequest {
  name?: string
  aliases?: string | null
  bridge_type?: string | null
  material?: string | null
  era?: string | null
  location?: string | null
  function?: string | null
  summary?: string | null
}

export interface BridgeMergeRequest {
  source_bridge_id: number
}

// --- Sources ---

export interface SourceListItem {
  id: number
  type: string
  title: string
  url: string | null
  chunk_count: number
  created_at: string
}

export interface SourceDetail {
  id: number
  type: string
  title: string
  url: string | null
  file_path: string | null
  accessed_at: string | null
  chunk_count: number
  created_at: string
}

// --- Taxonomy ---

export interface TaxonomyTreeItem {
  node_id: number
  label: string
  chunk_count: number
  children: TaxonomyTreeItem[]
}

export interface TaxonomyTree {
  items: TaxonomyTreeItem[]
}

export interface TaxonomyNodeDetail {
  id: number
  lvl1: string
  lvl2: string | null
  lvl3: string | null
  description: string | null
  chunk_count: number
}

export interface TaxonomyNodeCreate {
  lvl1: string
  lvl2?: string | null
  lvl3?: string | null
  description?: string | null
}

export interface TaxonomyBatchUpdate {
  chunk_ids: number[]
  lvl1: string
  lvl2?: string | null
  lvl3?: string | null
}

export interface TaxonomyBatchUpdateResult {
  updated_count: number
}

// --- Debug ---

export interface ChannelDebug {
  channel: string
  filter_desc: string
  vec_ids: number[]
  fts_ids: number[]
  rrf_scores: [number, number][]
  final_ids: number[]
}

export interface DebugInfo {
  facet: Record<string, unknown> | null
  channels: ChannelDebug[]
  timings: Record<string, number>
}

// --- System ---

export interface SystemStatus {
  version: string
  python_version: string
  db_connected: boolean
  db_version: string | null
  schema_version: number | null
  vector_dimension: number
  index_type: string
  llm_provider: string
  embedding_model: string
  chat_model: string
  chunk_quota: Record<string, number>
  rrf_k: number
  api_key_configured: boolean
}

// Auth
export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  user: UserInfo
}

export interface UserInfo {
  id: number
  username: string
  display_name: string | null
  is_active: boolean
  created_at: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

// Audit
export interface AuditLogItem {
  id: number
  user_id: number | null
  username: string | null
  action: string
  resource_type: string
  resource_id: string | null
  detail: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}
