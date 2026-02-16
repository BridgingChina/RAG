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
