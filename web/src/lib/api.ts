import type {
  AskResponse,
  AuditLogItem,
  BatchDeleteResponse,
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
  DownloadUrlResponse,
  IngestResponse,
  IngestTaskCreateRequest,
  IngestTaskItem,
  LoginRequest,
  LoginResponse,
  PaginatedResponse,
  PresignRequest,
  PresignResponse,
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
  chunkId: string

  constructor(currentUpdatedAt: string, chunkId: string) {
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
  targetBridgeId?: string | null,
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

// --- Ingest Tasks ---

export function presignIngestUpload(
  data: PresignRequest,
): Promise<PresignResponse> {
  return post<PresignResponse>("/ingest-tasks/presign", data)
}

export function createIngestTask(
  data: IngestTaskCreateRequest,
): Promise<IngestTaskItem> {
  return post<IngestTaskItem>("/ingest-tasks", data)
}

export function fetchIngestTasks(params?: {
  page?: number
  page_size?: number
  status?: string
  file_name?: string
}): Promise<PaginatedResponse<IngestTaskItem>> {
  return get<PaginatedResponse<IngestTaskItem>>("/ingest-tasks", params)
}

export function fetchIngestTask(id: string): Promise<IngestTaskItem> {
  return get<IngestTaskItem>(`/ingest-tasks/${id}`)
}

export function confirmIngestTask(id: string): Promise<IngestTaskItem> {
  return post<IngestTaskItem>(`/ingest-tasks/${id}/confirm`, {})
}

export function deleteIngestTask(id: string): Promise<void> {
  return del(`/ingest-tasks/${id}`)
}

export function retryIngestTask(id: string): Promise<IngestTaskItem> {
  return post<IngestTaskItem>(`/ingest-tasks/${id}/retry`, {})
}

export function batchDeleteIngestTasks(
  taskIds: string[],
): Promise<BatchDeleteResponse> {
  return post<BatchDeleteResponse>("/ingest-tasks/batch-delete", {
    task_ids: taskIds,
  })
}

export function getIngestTaskDownloadUrl(
  id: string,
  type: "raw" | "parsed",
): Promise<DownloadUrlResponse> {
  return get<DownloadUrlResponse>(`/ingest-tasks/${id}/download-url`, { type })
}

export async function uploadFileToR2(
  url: string,
  file: File,
  contentType: string,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", url)
    xhr.setRequestHeader("Content-Type", contentType)

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100))
        }
      }
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve()
      } else {
        reject(new Error(`Upload failed: HTTP ${xhr.status}`))
      }
    }

    xhr.onerror = () => reject(new Error("Upload failed: network error"))
    xhr.send(file)
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
  bridge_id?: string
  source_id?: string
  lvl1?: string
  lvl2?: string
  lvl3?: string
  binding_status?: string
  q?: string
}): Promise<PaginatedResponse<ChunkListItem>> {
  return get<PaginatedResponse<ChunkListItem>>("/chunks", params)
}

export function fetchChunk(id: string): Promise<ChunkDetail> {
  return get<ChunkDetail>(`/chunks/${id}`)
}

export function updateChunk(
  id: string,
  data: ChunkUpdateRequest,
): Promise<ChunkDetail> {
  return put<ChunkDetail>(`/chunks/${id}`, data)
}

export function deleteChunk(
  id: string,
  expectedUpdatedAt?: string,
): Promise<void> {
  const params = expectedUpdatedAt
    ? `?expected_updated_at=${encodeURIComponent(expectedUpdatedAt)}`
    : ""
  return del(`/chunks/${id}${params}`)
}

export function splitChunk(
  id: string,
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
  sourceId: string,
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

export function fetchBridge(id: string): Promise<BridgeDetail> {
  return get<BridgeDetail>(`/bridges/${id}`)
}

export function createBridge(data: BridgeCreateRequest): Promise<BridgeDetail> {
  return post<BridgeDetail>("/bridges", data)
}

export function updateBridge(
  id: string,
  data: BridgeUpdateRequest,
): Promise<BridgeDetail> {
  return put<BridgeDetail>(`/bridges/${id}`, data)
}

export function deleteBridge(id: string): Promise<void> {
  return del(`/bridges/${id}`)
}

export function fetchBridgeChunks(
  id: string,
  params?: { page?: number; page_size?: number },
): Promise<PaginatedResponse<ChunkListItem>> {
  return get<PaginatedResponse<ChunkListItem>>(`/bridges/${id}/chunks`, params)
}

export function mergeBridge(
  targetId: string,
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

export function fetchSource(id: string): Promise<SourceDetail> {
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
  id: string,
  data: { description?: string | null },
): Promise<TaxonomyNodeDetail> {
  return put<TaxonomyNodeDetail>(`/taxonomy/nodes/${id}`, data)
}

export function deleteTaxonomyNode(id: string): Promise<void> {
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
  user_id?: string
  action?: string
  resource_type?: string
  resource_id?: string
  start?: string
  end?: string
}): Promise<PaginatedResponse<AuditLogItem>> {
  return get<PaginatedResponse<AuditLogItem>>("/audit-logs", params)
}
