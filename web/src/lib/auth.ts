/**
 * Console auth client — talks to the unified auth Worker at
 * `auth.bridgingchina.net` (Better Auth + D1). Replaces the old
 * FastAPI-hosted /api/v1/auth/login flow that Phase 2 removed.
 */

export interface SessionUser {
  id: string
  email: string
  name?: string
  image?: string | null
  role?: string
}

export interface Session {
  user: SessionUser
  session: {
    id: string
    userId: string
    expiresAt: string
  }
}

const AUTH_BASE: string =
  (import.meta.env.VITE_AUTH_BASE_URL as string | undefined) ??
  "https://auth.bridgingchina.net"

interface CachedToken {
  token: string
  expiresAt: number
}

// JWT TTL is 15min (auth.ts:97). Cache for 14min (30s safety margin is not enough
// under clock drift — use 1min to be safe).
const TOKEN_CACHE_TTL_MS = 14 * 60 * 1000

let cachedToken: CachedToken | null = null

/**
 * Fetch a fresh JWT from the auth Worker. Returns null on no-session
 * (401/403) so callers can decide whether to redirect.
 */
async function fetchTokenFromWorker(): Promise<string | null> {
  const res = await fetch(`${AUTH_BASE}/api/auth/token`, {
    method: "GET",
    credentials: "include",
  })
  if (!res.ok) {
    // 401 = no session; anything else we also treat as "no usable token".
    return null
  }
  const data = (await res.json()) as { token?: string }
  return data.token ?? null
}

/**
 * Returns a Bearer JWT for the current session, using an in-memory
 * cache. Returns null if there is no valid session.
 */
export async function getJWT(): Promise<string | null> {
  if (cachedToken && Date.now() < cachedToken.expiresAt) {
    return cachedToken.token
  }
  const token = await fetchTokenFromWorker()
  if (!token) {
    cachedToken = null
    return null
  }
  cachedToken = { token, expiresAt: Date.now() + TOKEN_CACHE_TTL_MS }
  return token
}

/** Drop the cached token (e.g., after 401 on a downstream API call). */
export function clearJWTCache(): void {
  cachedToken = null
}

/**
 * Read the current session from the auth Worker. Not cached — role
 * changes must surface immediately on next guarded navigation.
 */
export async function getSession(): Promise<Session | null> {
  const res = await fetch(`${AUTH_BASE}/api/auth/get-session`, {
    method: "GET",
    credentials: "include",
  })
  if (!res.ok) return null
  const data = await res.json()
  // Better Auth returns `null` when there's no session; a signed-in session
  // comes back as { user, session }.
  if (!data || typeof data !== "object" || !("user" in data)) return null
  return data as Session
}

/**
 * Send the browser to the auth Worker's hosted login UI, remembering
 * where to come back to via ?redirect_to=.
 */
export function redirectToLogin(returnUrl?: string): void {
  const target = returnUrl ?? window.location.href
  const url = `${AUTH_BASE}/auth/login?redirect_to=${encodeURIComponent(target)}`
  window.location.href = url
}

export function authBaseUrl(): string {
  return AUTH_BASE
}

/**
 * Revoke the current session at the auth Worker and drop the cached JWT.
 * Callers typically follow up with `redirectToLogin()` so the user lands
 * back on the auth UI and can sign in again.
 */
export async function signOut(): Promise<void> {
  try {
    await fetch(`${AUTH_BASE}/api/auth/sign-out`, {
      method: "POST",
      credentials: "include",
    })
  } finally {
    clearJWTCache()
  }
}
