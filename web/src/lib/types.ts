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
