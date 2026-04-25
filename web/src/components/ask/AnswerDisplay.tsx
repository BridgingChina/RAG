import Markdown from "react-markdown"
import { AlertTriangle } from "lucide-react"
import type { AskResponse } from "@/lib/types"
import { ConfidenceBadge } from "./ConfidenceBadge"
import { EvidenceGrid } from "./EvidenceGrid"
import { DebugPanel } from "./DebugPanel"

export function AnswerDisplay({ data }: { data: AskResponse }) {
  return (
    <div className="rounded-lg border border-border bg-card p-6 space-y-5">
      {/* Degraded warning */}
      {data.degraded && data.degraded.length > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-[var(--yellow-hemp)]/10 border border-[var(--yellow-hemp)]/30 px-3 py-2 text-sm text-[var(--ink-black)]">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          部分功能降级：{data.degraded.join("、")}
        </div>
      )}

      {/* Confidence */}
      <ConfidenceBadge confidence={data.confidence} />

      {/* Summary */}
      <h2 className="font-serif text-2xl font-semibold text-foreground leading-snug">
        {data.summary}
      </h2>

      {/* Details */}
      <div className="prose prose-stone prose-sm max-w-none">
        <Markdown>{data.details}</Markdown>
      </div>

      {/* Analogy */}
      {data.analogy && (
        <blockquote className="border-l border-[var(--stone-grey-deep)] pl-4 text-sm text-muted-foreground italic">
          {data.analogy}
        </blockquote>
      )}

      {/* Evidence Grid */}
      {data.evidence_groups && <EvidenceGrid evidence={data.evidence_groups} />}

      {/* Citations */}
      {data.citations.length > 0 && (
        <div className="border-t border-border pt-4">
          <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-2">引用来源</h3>
          <ul className="space-y-1">
            {data.citations.map((c) => (
              <li key={c.chunk_id} className="text-xs text-muted-foreground">
                {c.source_title}
                {c.page_range && <span className="text-muted-foreground/60">（{c.page_range}）</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.debug && <DebugPanel debug={data.debug} />}
    </div>
  )
}
