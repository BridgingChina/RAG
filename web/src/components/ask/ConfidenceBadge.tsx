import type { ConfidenceResponse } from "@/lib/types"

const styles = {
  high: "bg-green-500 text-white",
  medium: "bg-yellow-400 text-yellow-900",
  low: "bg-red-500 text-white",
}

const labels = { high: "高置信", medium: "中置信", low: "低置信" }

export function ConfidenceBadge({ confidence }: { confidence: ConfidenceResponse }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[confidence.level]}`}>
        {labels[confidence.level]}
      </span>
      <span className="text-xs text-slate-400">{confidence.reason}</span>
    </div>
  )
}
