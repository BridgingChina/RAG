import { useNavigate } from "react-router"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/useApi"
import { fetchKnowledgePoint } from "@/lib/api"

interface KnowledgePointPreviewProps {
  kpId: string
}

export function KnowledgePointPreview({ kpId }: KnowledgePointPreviewProps) {
  const navigate = useNavigate()
  const { data: kp, loading, error } = useApi(
    () => fetchKnowledgePoint(kpId),
    [kpId],
  )

  if (loading && !kp) {
    return <Skeleton className="h-full w-full" />
  }
  if (error || !kp) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-destructive">
        {error || "加载知识点失败"}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold">{kp.name}</h2>
          {kp.aliases && (
            <p className="text-xs text-muted-foreground">别名：{kp.aliases}</p>
          )}
          <div className="flex gap-2 flex-wrap">
            {kp.difficulty && <Badge variant="secondary">{kp.difficulty}</Badge>}
            <Badge variant="outline">知识点</Badge>
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => navigate(`/knowledge-points/${kp.id}`)}>
          完整编辑
        </Button>
      </div>

      {kp.summary && (
        <div className="rounded-md border bg-muted/30 p-3">
          <h3 className="text-xs font-medium text-muted-foreground mb-1">简介</h3>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{kp.summary}</p>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium">要点（{kp.key_points.length}）</h3>
        </div>
        {kp.key_points.length === 0 ? (
          <p className="text-xs text-muted-foreground">尚未生成要点。去完整编辑页 → 生成要点。</p>
        ) : (
          <ol className="space-y-2">
            {kp.key_points.map((kpItem, idx) => (
              <li key={kpItem.id} className="rounded border p-2">
                <div className="text-sm font-medium">
                  {idx + 1}. {kpItem.summary}
                </div>
                {kpItem.explanation && (
                  <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">
                    {kpItem.explanation}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>

      {kp.l2_content && Object.keys(kp.l2_content).length > 0 && (
        <div className="rounded-md border p-3">
          <h3 className="text-xs font-medium text-muted-foreground mb-1">L2 扩展内容</h3>
          <p className="text-xs">已填（去完整编辑页查看/修改）</p>
        </div>
      )}
    </div>
  )
}
