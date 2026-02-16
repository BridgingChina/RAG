import { PageHeader } from "@/components/layout/PageHeader"
import { useApi } from "@/hooks/useApi"
import { fetchDashboardStats } from "@/lib/api"
import { StatCard } from "@/components/dashboard/StatCard"
import { DistributionBar } from "@/components/dashboard/DistributionBar"
import { IngestTimeline } from "@/components/dashboard/IngestTimeline"
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { Blocks, Landmark, FileText, AlertTriangle } from "lucide-react"

export function Component() {
  const { data, loading, error, refetch } = useApi(fetchDashboardStats)

  return (
    <>
      <PageHeader title="仪表盘" description="系统概览" />
      <main className="p-6">
        {loading && <LoadingState />}

        {error && (
          <div className="space-y-4">
            <p className="text-sm text-red-600">加载失败: {error}</p>
            <Button onClick={refetch} variant="outline" size="sm">
              重试
            </Button>
          </div>
        )}

        {data && (
          <div className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard
                title="知识块总数"
                value={data.chunk_count}
                icon={Blocks}
              />
              <StatCard
                title="桥梁总数"
                value={data.bridge_count}
                icon={Landmark}
              />
              <StatCard
                title="来源总数"
                value={data.source_count}
                icon={FileText}
              />
              <StatCard
                title="歧义占比"
                value={`${(data.ambiguous_ratio * 100).toFixed(1)}%`}
                icon={AlertTriangle}
              />
            </div>

            {/* Binding Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>绑定状态分布</CardTitle>
              </CardHeader>
              <CardContent>
                <DistributionBar
                  items={[
                    {
                      label: "绑定",
                      count: data.binding_distribution.primary,
                      color: "bg-emerald-500",
                    },
                    {
                      label: "歧义",
                      count: data.binding_distribution.ambiguous,
                      color: "bg-amber-500",
                    },
                    {
                      label: "未绑定",
                      count: data.binding_distribution.none,
                      color: "bg-gray-300",
                    },
                  ]}
                />
              </CardContent>
            </Card>

            {/* Lvl1 Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>知识分类分布</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {(() => {
                    const total = data.lvl1_distribution.reduce(
                      (sum, d) => sum + d.count,
                      0,
                    )
                    return data.lvl1_distribution.map((item) => {
                      const percentage =
                        total > 0 ? (item.count / total) * 100 : 0
                      return (
                        <div key={item.label} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">
                              {item.label}
                            </span>
                            <span className="font-medium">{item.count}</span>
                          </div>
                          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                            <div
                              className="h-full bg-blue-500"
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                        </div>
                      )
                    })
                  })()}
                  {data.lvl1_distribution.length === 0 && (
                    <p className="text-sm text-muted-foreground">暂无数据</p>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Recent Ingests */}
            <Card>
              <CardHeader>
                <CardTitle>最近入库</CardTitle>
              </CardHeader>
              <CardContent>
                <IngestTimeline items={data.recent_ingests} />
              </CardContent>
            </Card>
          </div>
        )}
      </main>
    </>
  )
}

function LoadingState() {
  return (
    <div className="space-y-6">
      {/* Stats Cards Loading */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div className="space-y-2">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-8 w-16" />
                </div>
                <Skeleton className="h-4 w-4 rounded" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Distribution Cards Loading */}
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-full rounded-md" />
          <div className="mt-3 flex gap-4">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-20" />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-24" />
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
