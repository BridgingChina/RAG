import type { AskResponse, IngestResponse } from "./types"

const BASE = "/api/v1"

async function request<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export function askQuestion(
  question: string,
  targetBridgeId?: number | null,
): Promise<AskResponse> {
  return request<AskResponse>("/ask", {
    question,
    target_bridge_id: targetBridgeId ?? null,
  })
}

export function ingestDocument(
  content: string,
  sourceType: string = "document",
): Promise<IngestResponse> {
  return request<IngestResponse>("/ingest", {
    content,
    source_type: sourceType,
  })
}
