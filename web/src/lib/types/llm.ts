/**
 * TypeScript types mirroring the Phase D `/api/v1/llm/*` Pydantic schemas.
 *
 * Zero-key-exposure invariant: response types intentionally omit `api_key_env`
 * and `extra_headers`. The admin UI surfaces only `has_api_key_configured`
 * (boolean) — the env var name never round-trips through the list/detail
 * responses. Input types DO carry `api_key_env` (admin is setting up routing)
 * but MUST NOT be re-used for display.
 *
 * Source of truth: app/api/v1/schemas/llm.py
 */

export type ProviderKind = "zhipu" | "openai_compat" | "minimax"

// ---------------------------------------------------------------------------
// Input shapes (create / update)
// ---------------------------------------------------------------------------

export interface ProviderCreateInput {
  name: string
  kind: ProviderKind
  base_url: string
  api_key_env: string
  extra_headers?: Record<string, string>
  enabled?: boolean
  timeout_read?: number
}

export interface ProviderUpdateInput {
  name?: string
  base_url?: string
  api_key_env?: string
  extra_headers?: Record<string, string>
  enabled?: boolean
  timeout_read?: number
}

export interface TaskRouteUpdateInput {
  task_key: string
  provider_id: string
  model_id: string
}

export interface TaskRouteBatchUpdateInput {
  updates: TaskRouteUpdateInput[]
}

// ---------------------------------------------------------------------------
// Response shapes (WHITELIST — zero-key-exposure)
// ---------------------------------------------------------------------------

export interface ProviderPublic {
  id: string
  name: string
  kind: ProviderKind
  base_url: string
  enabled: boolean
  timeout_read: number
  has_api_key_configured: boolean
  last_tested_at: string | null
  last_test_ok: boolean | null
  last_test_error: string | null
  model_count: number
  created_at: string
  updated_at: string
}

export interface ModelInfoPublic {
  id: string
  model_id: string
  display_name: string
  kind: string
  context_window: number | null
  fetched_at: string
}

export interface ProviderTestResult {
  status: "ok" | "fail"
  model_count: number
  reason: string | null
}

export interface TaskRoutePublic {
  task_key: string
  description: string
  provider_id: string
  provider_name: string
  model_id: string
  updated_at: string
  updated_by: string | null
}
