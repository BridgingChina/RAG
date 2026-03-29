import { PageHeader } from "@/components/layout/PageHeader"
import { useApi } from "@/hooks/useApi"
import { fetchSystemStatus } from "@/lib/api"
import type { SystemStatus } from "@/lib/types"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

function formatVersion(s: SystemStatus): string {
  const parts = [s.version]
  if (s.git_commit && s.git_commit !== "dev") {
    parts.push(s.git_date ? `${s.git_commit} (${s.git_date})` : s.git_commit)
  }
  return parts.join(" · ")
}

export function Component() {
  const { data, loading, error, refetch } = useApi(fetchSystemStatus)

  return (
    <>
      <PageHeader title="设置" description="系统状态与配置" />
      <main className="p-6">
        {loading && <LoadingState />}

        {error && (
          <div className="space-y-4">
            <p className="text-sm text-red-600">加载失败: {error}</p>
            <Button onClick={refetch} variant="outline" size="sm">重试</Button>
          </div>
        )}

        {data && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>系统状态</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <StatusRow label="数据库" connected={data.db_connected} detail={data.db_connected ? "已连接" : "未连接"} />
                <InfoRow label="Schema 版本" value={data.schema_version != null ? `v${data.schema_version}` : "未知"} />
                <StatusRow label="API 密钥" connected={data.api_key_configured} detail={data.api_key_configured ? "已配置" : "未配置"} />
                <InfoRow label="版本" value={formatVersion(data)} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>检索配置</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <InfoRow label="LLM 供应商" value={data.llm_provider} />
                <InfoRow label="嵌入模型" value={data.embedding_model} />
                <InfoRow label="对话模型" value={data.chat_model} />
                <InfoRow label="向量维度" value={String(data.vector_dimension)} />
                <InfoRow label="索引类型" value={data.index_type.toUpperCase()} />
                <InfoRow label="RRF k 值" value={String(data.rrf_k)} />
                <InfoRow label="通道配额" value={`Anchor ${data.chunk_quota.anchor} / Concept ${data.chunk_quota.concept} / Analogy ${data.chunk_quota.analogy}`} />
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </>
  )
}

function StatusRow({ label, connected, detail }: { label: string; connected: boolean; detail?: string | null }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2">
        <span className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-green-500" : "bg-red-500"}`} />
        <span className="font-medium">{detail ?? (connected ? "正常" : "异常")}</span>
      </span>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {[0, 1].map((i) => (
        <Card key={i}>
          <CardHeader><Skeleton className="h-6 w-24" /></CardHeader>
          <CardContent className="space-y-3">
            {[...Array(4)].map((_, j) => (
              <div key={j} className="flex justify-between">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-32" />
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
