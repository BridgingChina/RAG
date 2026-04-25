import { useState } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { testProvider } from "@/lib/api/llm"
import type { ProviderPublic } from "@/lib/types/llm"

interface ProviderCardProps {
  provider: ProviderPublic
  /** # of task routes currently pointing at this provider. */
  inUseCount: number
  onRefresh: () => void
  onEdit: () => void
  onDelete: () => void
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "未测试"
  const d = new Date(iso)
  return d.toLocaleString("zh-CN")
}

export function ProviderCard({
  provider,
  inUseCount,
  onRefresh,
  onEdit,
  onDelete,
}: ProviderCardProps) {
  const [testing, setTesting] = useState(false)
  const [testError, setTestError] = useState<string | null>(null)

  const keyOk = provider.has_api_key_configured
  const lastOk = provider.last_test_ok

  async function handleTest() {
    setTesting(true)
    setTestError(null)
    try {
      const result = await testProvider(provider.id)
      if (result.status === "fail") {
        setTestError(result.reason || "未知错误")
      }
      onRefresh()
    } catch (e) {
      setTestError(e instanceof Error ? e.message : String(e))
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{provider.name}</h3>
              <Badge variant="outline" className="font-mono text-xs">
                {provider.kind}
              </Badge>
              {!provider.enabled && (
                <Badge variant="secondary" className="text-xs">
                  已禁用
                </Badge>
              )}
              <Badge
                variant={keyOk ? "secondary" : "destructive"}
                className="text-xs"
              >
                {keyOk ? "✓ Key 已配" : "✗ Key 未配"}
              </Badge>
            </div>
            <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
              {provider.base_url}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <InfoRow label="模型数" value={String(provider.model_count)} />
          <InfoRow label="使用中" value={`${inUseCount} 个任务`} />
          <InfoRow
            label="超时"
            value={`${provider.timeout_read.toFixed(0)}s`}
          />
          <InfoRow
            label="最近测试"
            value={formatTimestamp(provider.last_tested_at)}
          />
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">状态：</span>
          {lastOk === null ? (
            <span className="text-muted-foreground">从未测试</span>
          ) : lastOk ? (
            <span className="text-[var(--songci-celadon-deep)]">正常</span>
          ) : (
            <span className="text-destructive">
              失败：{provider.last_test_error || "未知"}
            </span>
          )}
        </div>

        {testError && (
          <p className="text-xs text-destructive">测试失败：{testError}</p>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button size="sm" onClick={handleTest} disabled={testing}>
            {testing ? "测试中..." : "测试并刷新模型"}
          </Button>
          <Button size="sm" variant="outline" onClick={onEdit}>
            编辑
          </Button>
          <Button size="sm" variant="outline" onClick={onDelete}>
            删除
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
