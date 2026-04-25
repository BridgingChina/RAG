import type { ChannelDebug } from "@/lib/types"

export function DebugChannel({ data }: { data: ChannelDebug }) {
  const maxRows = Math.max(data.vec_ids.length, data.fts_ids.length, data.rrf_scores.length, data.final_ids.length)

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        筛选: <code className="text-xs bg-muted px-1 py-0.5 rounded">{data.filter_desc}</code>
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="text-left py-1 pr-4">Vector</th>
              <th className="text-left py-1 pr-4">FTS</th>
              <th className="text-left py-1 pr-4">RRF 融合</th>
              <th className="text-left py-1">最终选取</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {Array.from({ length: maxRows }, (_, i) => (
              <tr key={i} className="border-b border-dashed last:border-0">
                <td className="py-0.5 pr-4">{data.vec_ids[i] != null ? `#${data.vec_ids[i]}` : ""}</td>
                <td className="py-0.5 pr-4">{data.fts_ids[i] != null ? `#${data.fts_ids[i]}` : ""}</td>
                <td className="py-0.5 pr-4">
                  {data.rrf_scores[i] != null
                    ? `#${data.rrf_scores[i][0]} ${data.rrf_scores[i][1].toFixed(4)}`
                    : ""}
                </td>
                <td className="py-0.5">
                  {data.final_ids[i] != null ? (
                    <span className="text-[var(--songci-celadon)]">#{data.final_ids[i]}</span>
                  ) : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
