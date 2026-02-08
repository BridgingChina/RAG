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
}

export interface IngestedChunkSummary {
  content_preview: string
  lvl1: string | null
  lvl2: string | null
  bridge_name: string | null
}

export interface IngestResponse {
  source_id: number
  bridge_name: string | null
  title: string | null
  chunk_count: number
  chunks: IngestedChunkSummary[]
}
