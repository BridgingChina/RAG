import type { EvidenceGroupsResponse } from "@/lib/types"

interface ChannelConfig {
  key: keyof EvidenceGroupsResponse
  label: string
  color: string
}

// Channel accent colors: chart-1 (anchor), chart-4 (concept), chart-3 (analogy)
const channels: ChannelConfig[] = [
  { key: "anchor", label: "本桥资料", color: "bg-[var(--chart-1)]" },
  { key: "concept", label: "通用知识", color: "bg-[var(--chart-4)]" },
  { key: "analogy", label: "类比案例", color: "bg-[var(--chart-3)]" },
]

export function EvidenceGrid({ evidence }: { evidence: EvidenceGroupsResponse }) {
  const hasAny = evidence.anchor.length + evidence.concept.length + evidence.analogy.length > 0
  if (!hasAny) return null

  return (
    <div className="border-t border-border pt-5">
      <h3 className="text-xs uppercase tracking-wider text-muted-foreground mb-3">检索证据</h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {channels.map(({ key, label, color }) => (
          <div key={key} className="space-y-2">
            <div className={`h-1 w-full rounded-full ${color}`} />
            <h4 className="text-xs uppercase tracking-wider text-muted-foreground font-medium">
              {label}
            </h4>
            {evidence[key].length === 0 ? (
              <p className="text-xs text-muted-foreground/50">无</p>
            ) : (
              <ul className="space-y-2">
                {evidence[key].map((chunk) => (
                  <li
                    key={chunk.chunk_id}
                    className="rounded-lg border border-border bg-card p-2.5"
                  >
                    <p className="text-xs text-foreground/70 leading-relaxed line-clamp-3">
                      {chunk.preview}
                    </p>
                    {chunk.bridge_name && (
                      <p className="mt-1 text-[11px] text-muted-foreground">{chunk.bridge_name}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
