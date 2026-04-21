/**
 * Thin client wrappers for the Phase D `/api/v1/llm/*` endpoints.
 *
 * Every function is a one-liner that delegates to the shared `get`/`post`/
 * `put`/`del`/`patch` helpers in `lib/api.ts` — the auth header, BASE URL
 * prefix, and unified error handling all live there. Do NOT reintroduce
 * `fetch` here.
 *
 * All endpoints require admin JWT; unauthorized calls bounce via
 * `parseHttpError` → `handleUnauthorized` in the shared layer.
 */
import { del, get, patch, post, put } from "@/lib/api"
import type {
  ModelInfoPublic,
  ProviderCreateInput,
  ProviderPublic,
  ProviderTestResult,
  ProviderUpdateInput,
  TaskRouteBatchUpdateInput,
  TaskRoutePublic,
  TaskRouteUpdateInput,
} from "@/lib/types/llm"

// ---------------------------------------------------------------------------
// Providers (5 endpoints)
// ---------------------------------------------------------------------------

export function listProviders(enabled?: boolean): Promise<ProviderPublic[]> {
  return get<ProviderPublic[]>(
    "/llm/providers",
    enabled === undefined ? undefined : { enabled },
  )
}

export function createProvider(
  body: ProviderCreateInput,
): Promise<ProviderPublic> {
  return post<ProviderPublic>("/llm/providers", body)
}

export function getProvider(providerId: string): Promise<ProviderPublic> {
  return get<ProviderPublic>(`/llm/providers/${providerId}`)
}

export function updateProvider(
  providerId: string,
  body: ProviderUpdateInput,
): Promise<ProviderPublic> {
  return patch<ProviderPublic>(`/llm/providers/${providerId}`, body)
}

export function deleteProvider(providerId: string): Promise<void> {
  return del(`/llm/providers/${providerId}`)
}

// ---------------------------------------------------------------------------
// Test & models (2 endpoints)
// ---------------------------------------------------------------------------

export function testProvider(providerId: string): Promise<ProviderTestResult> {
  return post<ProviderTestResult>(`/llm/providers/${providerId}/test`, {})
}

export function listProviderModels(
  providerId: string,
): Promise<ModelInfoPublic[]> {
  return get<ModelInfoPublic[]>(`/llm/providers/${providerId}/models`)
}

// ---------------------------------------------------------------------------
// Tasks (3 endpoints)
// ---------------------------------------------------------------------------

export function listTasks(): Promise<TaskRoutePublic[]> {
  return get<TaskRoutePublic[]>("/llm/tasks")
}

export function updateTaskRoute(
  taskKey: string,
  body: TaskRouteUpdateInput,
): Promise<TaskRoutePublic> {
  return put<TaskRoutePublic>(`/llm/tasks/${taskKey}`, body)
}

export function batchUpdateTaskRoutes(
  body: TaskRouteBatchUpdateInput,
): Promise<TaskRoutePublic[]> {
  return post<TaskRoutePublic[]>("/llm/tasks/batch-update", body)
}

// ---------------------------------------------------------------------------
// Cache control (1 endpoint)
// ---------------------------------------------------------------------------

export function invalidateRouteCache(): Promise<void> {
  return post<void>("/llm/routes/invalidate-cache", {})
}
