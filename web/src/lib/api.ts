import type {
  AskResponse,
  AuditLogItem,
  BridgeCreateRequest,
  BridgeDetail,
  BridgeListItem,
  BridgeMergeRequest,
  BridgeUpdateRequest,
  ChangePasswordRequest,
  ChunkBatchRequest,
  ChunkDetail,
  ChunkListItem,
  ChunkMergeRequest,
  ChunkSplitRequest,
  ChunkSplitResponse,
  ChunkUpdateRequest,
  DashboardStats,
  IngestResponse,
  LoginRequest,
  LoginResponse,
  PaginatedResponse,
  ReindexResponse,
  SourceDetail,
  SourceListItem,
  SystemStatus,
  TaxonomyBatchUpdate,
  TaxonomyBatchUpdateResult,
  TaxonomyNodeCreate,
  TaxonomyNodeDetail,
  TaxonomyTree,
  UserInfo,
} from "./types"

const BASE = "/api/v1"

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("auth-token")
  if (token) {
    return { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
  }
  return { "Content-Type": "application/json" }
}

export class ConflictError extends Error {
  currentUpdatedAt: string
  chunkId: number

  constructor(currentUpdatedAt: string, chunkId: number) {
    super("Chunk has been modified by another user")
    this.name = "ConflictError"
    this.currentUpdatedAt = currentUpdatedAt
    this.chunkId = chunkId
  }
}

// --- Core HTTP methods ---

async function get<T>(
  url: string,
  params?: Record<string, unknown>,
): Promise<T> {
  let fullUrl = `${BASE}${url}`

  if (params) {
    // Build query string, ignoring null/undefined/empty string values
    const searchParams = new URLSearchParams()
    for (const [key, value] of Object.entries(params)) {
      if (value !== null && value !== undefined && value !== "") {
        searchParams.append(key, String(value))
      }
    }
    const queryString = searchParams.toString()
    if (queryString) {
      fullUrl += `?${queryString}`
    }
  }

  const res = await fetch(fullUrl, {
    method: "GET",
    headers: authHeaders(),
  })

  if (!res.ok) {
    const text = await res.text()
    if (res.status === 401) {
      localStorage.removeItem("auth-token")
      window.location.href = "/login"
    }
    throw new Error(text || `HTTP ${res.status}`)
  }

  return res.json()
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const text = await res.text()
    if (res.status === 401) {
      localStorage.removeItem("auth-token")
      window.location.href = "/login"
    }
    if (res.status === 409) {
      const data = JSON.parse(text)
      throw new ConflictError(data.current_updated_at, data.chunk_id)
    }
    throw new Error(text || `HTTP ${res.status}`)
  }

  return res.json()
}

async function put<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const text = await res.text()
    if (res.status === 401) {
      localStorage.removeItem("auth-token")
      window.location.href = "/login"
    }
    if (res.status === 409) {
      const data = JSON.parse(text)
      throw new ConflictError(data.current_updated_at, data.chunk_id)
    }
    throw new Error(text || `HTTP ${res.status}`)
  }

  return res.json()
}

async function del(url: string): Promise<void> {
  const res = await fetch(`${BASE}${url}`, {
    method: "DELETE",
    headers: authHeaders(),
  })

  if (!res.ok) {
    const text = await res.text()
    if (res.status === 401) {
      localStorage.removeItem("auth-token")
      window.location.href = "/login"
    }
    if (res.status === 409) {
      const data = JSON.parse(text)
      throw new ConflictError(data.current_updated_at, data.chunk_id)
    }
    throw new Error(text || `HTTP ${res.status}`)
  }
}

async function patch<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "PATCH",
    headers: authHeaders(),
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    const text = await res.text()
    if (res.status === 401) {
      localStorage.removeItem("auth-token")
      window.location.href = "/login"
    }
    if (res.status === 409) {
      const data = JSON.parse(text)
      throw new ConflictError(data.current_updated_at, data.chunk_id)
    }
    throw new Error(text || `HTTP ${res.status}`)
  }

  return res.json()
}

// --- Ask & Ingest (existing endpoints) ---

export function askQuestion(
  question: string,
  targetBridgeId?: number | null,
  debug?: boolean,
): Promise<AskResponse> {
  return post<AskResponse>("/ask", {
    question,
    target_bridge_id: targetBridgeId ?? null,
    debug: debug ?? false,
  })
}

export function ingestDocument(
  content: string,
  sourceType: string = "document",
  options?: {
    bridgeCandidates?: string[] | null
    minPrimaryConfidence?: number
    enableAutoBridgeDetection?: boolean
  },
): Promise<IngestResponse> {
  return post<IngestResponse>("/ingest", {
    content,
    source_type: sourceType,
    bridge_candidates: options?.bridgeCandidates ?? null,
    min_primary_confidence: options?.minPrimaryConfidence ?? 0.75,
    enable_auto_bridge_detection: options?.enableAutoBridgeDetection ?? true,
  })
}

// --- Dashboard ---

export function fetchDashboardStats(): Promise<DashboardStats> {
  return get<DashboardStats>("/stats/dashboard")
}

// --- Chunks ---

export function fetchChunks(params?: {
  page?: number
  page_size?: number
  bridge_id?: number
  source_id?: number
  lvl1?: string
  lvl2?: string
  lvl3?: string
  binding_status?: string
  q?: string
}): Promise<PaginatedResponse<ChunkListItem>> {
  return get<PaginatedResponse<ChunkListItem>>("/chunks", params)
}

export function fetchChunk(id: number): Promise<ChunkDetail> {
  return get<ChunkDetail>(`/chunks/${id}`)
}

export function updateChunk(
  id: number,
  data: ChunkUpdateRequest,
): Promise<ChunkDetail> {
  return put<ChunkDetail>(`/chunks/${id}`, data)
}

export function deleteChunk(
  id: number,
  expectedUpdatedAt?: string,
): Promise<void> {
  const params = expectedUpdatedAt
    ? `?expected_updated_at=${encodeURIComponent(expectedUpdatedAt)}`
    : ""
  return del(`/chunks/${id}${params}`)
}

export function splitChunk(
  id: number,
  data: ChunkSplitRequest,
): Promise<ChunkSplitResponse> {
  return post<ChunkSplitResponse>(`/chunks/${id}/split`, data)
}

export function mergeChunks(data: ChunkMergeRequest): Promise<ChunkDetail> {
  return post<ChunkDetail>("/chunks/merge", data)
}

export function batchChunks(
  data: ChunkBatchRequest,
): Promise<{ updated?: number; deleted?: number }> {
  return patch<{ updated?: number; deleted?: number }>("/chunks/batch", data)
}

export function reindexSource(
  sourceId: number,
  force = false,
): Promise<ReindexResponse> {
  return post<ReindexResponse>(`/sources/${sourceId}/reindex?force=${force}`, {})
}

// --- Bridges ---

export function fetchBridges(params?: {
  page?: number
  page_size?: number
  q?: string
}): Promise<PaginatedResponse<BridgeListItem>> {
  return get<PaginatedResponse<BridgeListItem>>("/bridges", params)
}

export function fetchBridge(id: number): Promise<BridgeDetail> {
  return get<BridgeDetail>(`/bridges/${id}`)
}

export function createBridge(data: BridgeCreateRequest): Promise<BridgeDetail> {
  return post<BridgeDetail>("/bridges", data)
}

export function updateBridge(
  id: number,
  data: BridgeUpdateRequest,
): Promise<BridgeDetail> {
  return put<BridgeDetail>(`/bridges/${id}`, data)
}

export function deleteBridge(id: number): Promise<void> {
  return del(`/bridges/${id}`)
}

export function fetchBridgeChunks(
  id: number,
  params?: { page?: number; page_size?: number },
): Promise<PaginatedResponse<ChunkListItem>> {
  return get<PaginatedResponse<ChunkListItem>>(`/bridges/${id}/chunks`, params)
}

export function mergeBridge(
  targetId: number,
  data: BridgeMergeRequest,
): Promise<BridgeDetail> {
  return post<BridgeDetail>(`/bridges/${targetId}/merge`, data)
}

// --- Sources ---

export function fetchSources(params?: {
  page?: number
  page_size?: number
  q?: string
  type?: string
}): Promise<PaginatedResponse<SourceListItem>> {
  return get<PaginatedResponse<SourceListItem>>("/sources", params)
}

export function fetchSource(id: number): Promise<SourceDetail> {
  return get<SourceDetail>(`/sources/${id}`)
}

// --- Taxonomy ---

export function fetchTaxonomyTree(): Promise<TaxonomyTree> {
  return get<TaxonomyTree>("/taxonomy/tree")
}

export function createTaxonomyNode(data: TaxonomyNodeCreate): Promise<TaxonomyNodeDetail> {
  return post<TaxonomyNodeDetail>("/taxonomy/nodes", data)
}

export function updateTaxonomyNode(
  id: number,
  data: { description?: string | null },
): Promise<TaxonomyNodeDetail> {
  return put<TaxonomyNodeDetail>(`/taxonomy/nodes/${id}`, data)
}

export function deleteTaxonomyNode(id: number): Promise<void> {
  return del(`/taxonomy/nodes/${id}`)
}

export function batchUpdateTaxonomy(
  data: TaxonomyBatchUpdate,
): Promise<TaxonomyBatchUpdateResult> {
  return post<TaxonomyBatchUpdateResult>("/taxonomy/batch-update", data)
}

// --- System ---

export function fetchSystemStatus(): Promise<SystemStatus> {
  return get<SystemStatus>("/system/status")
}

// --- Auth ---

export function login(data: LoginRequest): Promise<LoginResponse> {
  return fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `HTTP ${res.status}`)
    }
    return res.json()
  })
}

export function fetchMe(): Promise<UserInfo> {
  return get<UserInfo>("/auth/me")
}

export function changePassword(data: ChangePasswordRequest): Promise<void> {
  return put<void>("/auth/password", data)
}

// --- Audit ---

export function fetchAuditLogs(params?: {
  page?: number
  page_size?: number
  user_id?: number
  action?: string
  resource_type?: string
  start?: string
  end?: string
}): Promise<PaginatedResponse<AuditLogItem>> {
  return get<PaginatedResponse<AuditLogItem>>("/audit-logs", params)
}
