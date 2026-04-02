import type { ChunkDetail, BridgeLinkInput, TaxonomyTreeItem } from "@/lib/types"

// --- Bridge link row (form state) ---

export interface BridgeLinkRow {
  bridge_id: string
  role: "primary" | "secondary" | "candidate"
  confidence: string
}

export function bridgeLinkRowsFromDetail(
  links: ChunkDetail["bridge_links"],
): BridgeLinkRow[] {
  return links.map((l) => ({
    bridge_id: String(l.bridge_id),
    role: l.role as "primary" | "secondary" | "candidate",
    confidence: String(l.confidence),
  }))
}

export function bridgeLinkRowsToInput(rows: BridgeLinkRow[]): BridgeLinkInput[] {
  return rows
    .filter((r) => r.bridge_id.trim() !== "")
    .map((r) => ({
      bridge_id: r.bridge_id,
      role: r.role,
      confidence: Number.isNaN(Number(r.confidence))
        ? 1.0
        : Number(r.confidence),
      method: "manual" as const,
    }))
}

// --- Taxonomy cascade helpers ---

export function getLvl1Options(items: TaxonomyTreeItem[]): TaxonomyTreeItem[] {
  return items
}

export function getLvl2Options(
  items: TaxonomyTreeItem[],
  lvl1: string | null,
): TaxonomyTreeItem[] {
  if (!lvl1) return []
  const parent = items.find((i) => i.label === lvl1)
  return parent?.children ?? []
}

export function getLvl3Options(
  items: TaxonomyTreeItem[],
  lvl1: string | null,
  lvl2: string | null,
): TaxonomyTreeItem[] {
  if (!lvl1 || !lvl2) return []
  const parent = items.find((i) => i.label === lvl1)
  const sub = parent?.children.find((i) => i.label === lvl2)
  return sub?.children ?? []
}

// --- Stale count helper ---

export function staleCount(chunks: { needs_reindex: boolean }[]): number {
  return chunks.filter((c) => c.needs_reindex).length
}

// --- Split helpers ---

export interface ParagraphSegment {
  text: string
  startOffset: number
  endOffset: number
}

export function parseContentSegments(content: string): ParagraphSegment[] {
  const separator = content.includes("\n\n") ? "\n\n" : "\n"
  const parts = content.split(separator)

  const segments: ParagraphSegment[] = []
  let offset = 0
  for (let i = 0; i < parts.length; i++) {
    const text = parts[i]
    if (text.length > 0) {
      segments.push({
        text,
        startOffset: offset,
        endOffset: offset + text.length,
      })
    }
    offset += text.length
    if (i < parts.length - 1) {
      offset += separator.length
    }
  }
  return segments
}

export function segmentBgClass(i: number, hoveredIdx: number | null): string {
  if (hoveredIdx === null) return ""
  return i < hoveredIdx ? "bg-blue-50" : "bg-emerald-50"
}
