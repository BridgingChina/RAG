import { Badge } from "@/components/ui/badge"
import type { IngestedChunkSummary } from "@/lib/types"

export function ChunkList({ chunks }: { chunks: IngestedChunkSummary[] }) {
  if (chunks.length === 0) return null

  return (
    <ul className="divide-y divide-border">
      {chunks.map((chunk, i) => (
        <li key={i} className="py-2.5 flex items-start justify-between gap-3">
          <p className="text-sm text-foreground/70 truncate flex-1">
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
            {chunk.primary_bridge_name && (
              <span className="text-[11px] text-muted-foreground">{chunk.primary_bridge_name}</span>
            )}
            {chunk.binding_status !== "none" && (
              <Badge
                variant="secondary"
                className="text-[11px]"
              >
                {chunk.binding_status}
              </Badge>
            )}
            {chunk.secondary_bridge_names.length > 0 && (
              <span className="text-[11px] text-muted-foreground">
                +{chunk.secondary_bridge_names.length} 次要桥
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}
