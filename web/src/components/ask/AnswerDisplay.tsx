import Markdown from "react-markdown"
import { AlertTriangle } from "lucide-react"
import type { AskResponse } from "@/lib/types"
import { ConfidenceBadge } from "./ConfidenceBadge"
import { EvidenceGrid } from "./EvidenceGrid"
import { DebugPanel } from "./DebugPanel"

export function AnswerDisplay({ data }: { data: AskResponse }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-5">
      {/* Degraded warning */}
      {data.degraded && data.degraded.length > 0 && (
        <div className="flex items-center gap-2 rounded-md bg-yellow-50 border border-yellow-200 px-3 py-2 text-sm text-yellow-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          部分功能降级：{data.degraded.join("、")}
        </div>
      )}

      {/* Confidence */}
      <ConfidenceBadge confidence={data.confidence} />

      {/* Summary */}
      <h2 className="font-serif text-2xl font-semibold text-slate-800 leading-snug">
        {data.summary}
      </h2>

      {/* Details */}
      <div className="prose prose-slate prose-sm max-w-none">
        <Markdown>{data.details}</Markdown>
      </div>

      {/* Analogy */}
      {data.analogy && (
        <blockquote className="border-l-4 border-blue-400 pl-4 text-sm text-slate-600 italic">
          {data.analogy}
        </blockquote>
      )}

      {/* Evidence Grid */}
      {data.evidence_groups && <EvidenceGrid evidence={data.evidence_groups} />}

      {/* Citations */}
      {data.citations.length > 0 && (
        <div className="border-t border-slate-100 pt-4">
          <h3 className="text-xs uppercase tracking-wider text-slate-400 mb-2">引用来源</h3>
          <ul className="space-y-1">
            {data.citations.map((c) => (
              <li key={c.chunk_id} className="text-xs text-slate-500">
                {c.source_title}
                {c.page_range && <span className="text-slate-400">（{c.page_range}）</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.debug && <DebugPanel debug={data.debug} />}
    </div>
  )
}
