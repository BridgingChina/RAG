// --- Ask ---

export interface AskRequest {
  question: string
  target_bridge_id?: string | null
}

export interface CitationResponse {
  chunk_id: string
  source_title: string
  page_range: string | null
}

export interface ConfidenceResponse {
  level: "high" | "medium" | "low"
  reason: string
}

export interface ChunkSummary {
  chunk_id: string
  bridge_id: string | null
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
  source_id: string
  title: string | null
  primary_bridge_names: string[]
  ambiguous_chunk_count: number
  auto_created_bridges: string[]
  chunk_count: number
  chunks: IngestedChunkSummary[]
}

// --- Ingest Tasks ---

export type IngestTaskStatus =
  | "uploading"
  | "syncing"
  | "parsing"
  | "chunked"
  | "indexing"
  | "completed"
  | "failed"
  | "deleted"

export interface IngestTaskItem {
  id: string
  status: IngestTaskStatus
  file_name: string
  file_type: string
  file_size: number | null
  source_id: string | null
  chunk_count: number | null
  image_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface PresignRequest {
  file_name: string
  file_type: string
  file_size: number
  content_type: string
}

export interface PresignResponse {
  upload_url: string
  r2_key: string
}

export interface IngestTaskCreateRequest {
  file_name: string
  file_type: string
  file_size: number
  r2_key: string
}

export interface BatchDeleteRequest {
  task_ids: string[]
}

export interface BatchDeleteResponse {
  deleted: string[]
  skipped: string[]
}

export interface DownloadUrlResponse {
  url: string
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
  source_id: string
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
  id: string
  content_preview: string
  bridge_id: string | null
  bridge_name: string | null
  lvl1: string | null
  lvl2: string | null
  binding_status: string
  source_id: string
  source_title: string | null
  created_at: string
  needs_reindex: boolean
  updated_at: string
}

export interface ChunkBridgeLinkDetail {
  id: string
  bridge_id: string
  bridge_name: string | null
  role: string
  confidence: number
  method: string
}

export interface ChunkDetail {
  id: string
  content: string
  contextual_text: string | null
  search_text: string | null
  section_title: string | null
  page_range: string | null
  lvl1: string | null
  lvl2: string | null
  lvl3: string | null
  bridge_id: string | null
  bridge_name: string | null
  binding_status: string
  source_id: string
  source_title: string | null
  created_at: string
  bridge_links: ChunkBridgeLinkDetail[]
  needs_reindex: boolean
  updated_at: string
}

export interface ChunkUpdateRequest {
  lvl1?: string | null
  lvl2?: string | null
  lvl3?: string | null
  bridge_id?: string | null
  binding_status?: "none" | "primary" | "ambiguous"
  content?: string | null
  section_title?: string | null
  bridge_links?: BridgeLinkInput[] | null
  expected_updated_at?: string
}

export interface BridgeLinkInput {
  bridge_id: string
  role: "primary" | "secondary" | "candidate"
  confidence?: number
  method?: "hint" | "rule" | "llm" | "manual"
}

export interface ChunkSplitRequest {
  position: number
  expected_updated_at?: string
}

export interface ChunkSplitResponse {
  chunks: ChunkDetail[]
}

export interface ChunkMergeRequest {
  chunk_ids: string[]
}

export interface ChunkBatchUpdate {
  lvl1?: string | null
  lvl2?: string | null
  lvl3?: string | null
  bridge_id?: string | null
  binding_status?: "none" | "primary" | "ambiguous"
}

export interface ChunkBatchRequest {
  chunk_ids: string[]
  action: "update" | "delete"
  updates?: ChunkBatchUpdate
}

export interface ReindexResponse {
  source_id: string
  chunks_reindexed: number
  chunks_failed: string[]
}

// --- Bridges ---

export interface BridgeListItem {
  id: string
  name: string
  aliases: string | null
  bridge_type: string | null
  material: string | null
  era: string | null
  region: string | null
  latitude: number | null
  longitude: number | null
  chunk_count: number
  created_at: string
}

export interface BridgeDetail {
  id: string
  name: string
  aliases: string | null
  bridge_type: string | null
  material: string | null
  era: string | null
  region: string | null
  latitude: number | null
  longitude: number | null
  function: string | null
  summary: string | null
  geocode_source: string | null
  chunk_count: number
  created_at: string
}

export type ImageType = "photo" | "illustration" | "map"

export interface BridgeImage {
  id: string
  bridge_id: string
  url: string
  caption: string | null
  type: ImageType | null
  order_index: number
  created_at: string
}

export interface BridgeCreateRequest {
  name: string
  aliases?: string | null
  bridge_type?: string | null
  material?: string | null
  era?: string | null
  region?: string | null
  latitude?: number | null
  longitude?: number | null
  function?: string | null
  summary?: string | null
}

export interface BridgeUpdateRequest {
  name?: string
  aliases?: string | null
  bridge_type?: string | null
  material?: string | null
  era?: string | null
  region?: string | null
  latitude?: number | null
  longitude?: number | null
  function?: string | null
  summary?: string | null
}

export interface BridgeMergeRequest {
  source_bridge_id: string
}

// --- Sources ---

export interface SourceListItem {
  id: string
  type: string
  title: string
  url: string | null
  chunk_count: number
  created_at: string
}

export interface SourceDetail {
  id: string
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
  node_id: string
  label: string
  chunk_count: number
  children: TaxonomyTreeItem[]
}

export interface TaxonomyTree {
  items: TaxonomyTreeItem[]
}

export interface TaxonomyNodeDetail {
  id: string
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
  chunk_ids: string[]
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
  vec_ids: string[]
  fts_ids: string[]
  rrf_scores: [string, number][]
  final_ids: string[]
}

export interface DebugInfo {
  facet: Record<string, unknown> | null
  channels: ChannelDebug[]
  timings: Record<string, number>
}

// --- System ---

export interface SystemStatus {
  version: string
  git_commit: string
  git_date: string
  python_version: string
  db_connected: boolean
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
  id: string
  username: string
  display_name: string | null
  is_active: boolean
  created_at: string
}

export interface ChangePasswordRequest {
  current_password: string
  new_password: string
}

// --- Knowledge Points ---

export interface KnowledgePointListItem {
  id: string
  name: string
  taxonomy_node_id: string | null
  difficulty: string | null
  summary: string | null
}

export interface KeyPointItem {
  id: string
  summary: string
  explanation: string | null
  order_index: number
  chunk_ids: string[]
}

export interface KnowledgePointDetail {
  id: string
  taxonomy_node_id: string | null
  name: string
  aliases: string | null
  difficulty: string | null
  summary: string | null
  l2_content: L2Content | null
  key_points: KeyPointItem[]
}

export interface L2Content {
  comparisons?: Array<{ title: string; content: string }>
  evolution?: string
  controversies?: Array<{ title: string; description: string }>
  further_reading?: Array<{ title: string; source_id?: string }>
}

export interface KPBridgeItem {
  id: string
  bridge_id: string
  bridge_name: string
  relevance_note: string | null
  order_index: number
}

// Audit
export interface AuditLogItem {
  id: string
  user_id: string | null
  username: string | null
  action: string
  resource_type: string
  resource_id: string | null
  detail: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}
