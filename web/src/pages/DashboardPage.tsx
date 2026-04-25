import { PageHeader } from "@/components/layout/PageHeader"
import { useApi } from "@/hooks/useApi"
import { fetchDashboardStats } from "@/lib/api"
import { StatCard } from "@/components/dashboard/StatCard"
import { BindingPieChart } from "@/components/dashboard/BindingPieChart"
import { Lvl1BarChart } from "@/components/dashboard/Lvl1BarChart"
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
            <p className="text-sm text-destructive">加载失败: {error}</p>
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
                <BindingPieChart distribution={data.binding_distribution} />
              </CardContent>
            </Card>

            {/* Lvl1 Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>知识分类分布</CardTitle>
              </CardHeader>
              <CardContent>
                <Lvl1BarChart data={data.lvl1_distribution} />
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
