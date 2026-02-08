import { Badge } from "@/components/ui/badge"
import type { IngestedChunkSummary } from "@/lib/types"

export function ChunkList({ chunks }: { chunks: IngestedChunkSummary[] }) {
  if (chunks.length === 0) return null

  return (
    <ul className="divide-y divide-slate-100">
      {chunks.map((chunk, i) => (
        <li key={i} className="py-2.5 flex items-start justify-between gap-3">
          <p className="text-sm text-slate-600 truncate flex-1">
            {chunk.content_preview}
          </p>
          <div className="flex items-center gap-1.5 shrink-0">
            {chunk.lvl1 && (
              <Badge variant="secondary" className="text-[11px]">
                {chunk.lvl1}
              </Badge>
            )}
            {chunk.lvl2 && (
              <Badge variant="secondary" className="text-[11px]">
                {chunk.lvl2}
              </Badge>
            )}
            {chunk.bridge_name && (
              <span className="text-[11px] text-slate-400">{chunk.bridge_name}</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
