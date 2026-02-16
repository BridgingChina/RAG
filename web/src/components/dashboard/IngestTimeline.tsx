import type { RecentIngest } from "@/lib/types"
import { Badge } from "@/components/ui/badge"

interface IngestTimelineProps {
  items: RecentIngest[]
}

export function IngestTimeline({ items }: IngestTimelineProps) {
  if (items.length === 0) {
    return (
      <p className="py-4 text-sm text-muted-foreground">暂无入库记录</p>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((item) => {
        const date = new Date(item.created_at).toLocaleDateString("zh-CN")
        return (
          <div
            key={item.source_id}
            className="flex items-center justify-between border-b pb-3 last:border-b-0 last:pb-0"
          >
            <div className="flex-1 space-y-1">
              <p className="text-sm font-medium">
                {item.title || "无标题"}
              </p>
              <p className="text-xs text-muted-foreground">{date}</p>
            </div>
            <Badge variant="secondary" className="ml-4">
              {item.chunk_count} 块
            </Badge>
          </div>
        )
      })}
    </div>
  )
}
