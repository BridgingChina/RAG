import type { ConfidenceResponse } from "@/lib/types"

// Confidence dot colors map to DESIGN.md signal convention:
// high → songci-celadon, medium → yellow-hemp, low → vermilion
const styles = {
  high: "bg-[var(--songci-celadon)] text-[var(--xuan-white)]",
  medium: "bg-[var(--yellow-hemp)] text-[var(--ink-black)]",
  low: "bg-[var(--vermilion)] text-[var(--xuan-white)]",
}

const labels = { high: "高置信", medium: "中置信", low: "低置信" }

export function ConfidenceBadge({ confidence }: { confidence: ConfidenceResponse }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[confidence.level]}`}>
        {labels[confidence.level]}
      </span>
      <span className="text-xs text-muted-foreground">{confidence.reason}</span>
    </div>
  )
}
