import { useParams, useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useApi } from "@/hooks/useApi"
import { fetchSource, fetchChunks } from "@/lib/api"

// Helper function for source type badge variant
function getTypeVariant(type: string) {
  if (type === "pdf") return "default"
  if (type === "web") return "secondary"
  if (type === "note") return "outline"
  return "secondary"
}

// Helper function for binding status badge variant
function getBindingVariant(status: string) {
  if (status === "primary") return "default"
  if (status === "ambiguous") return "destructive"
  return "secondary"
}

// Helper function for binding status label
function getBindingLabel(status: string) {
  if (status === "primary") return "绑定"
  if (status === "ambiguous") return "歧义"
  return "未绑定"
}

export function Component() {
  const { id } = useParams()
  const navigate = useNavigate()

  const { data: source, loading, error } = useApi(
    () => fetchSource(Number(id)),
    [id],
  )

  const { data: chunksData } = useApi(
    () => fetchChunks({ source_id: Number(id) }),
    [id],
  )

  if (loading) {
    return (
      <>
        <PageHeader title="来源详情" />
        <main className="space-y-6 p-6">
          <Skeleton className="h-96 w-full" />
          <Skeleton className="h-64 w-full" />
        </main>
      </>
    )
  }

  if (error || !source) {
    return (
      <>
        <PageHeader title="来源详情" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">
              {error || "未找到来源"}
            </p>
            <Button onClick={() => navigate("/sources")} variant="outline">
              返回列表
            </Button>
          </div>
        </main>
      </>
    )
  }

  const chunks = chunksData?.items || []

  return (
    <>
      <PageHeader title="来源详情">
        <Button onClick={() => navigate("/sources")} variant="outline">
          返回列表
        </Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {/* Source Metadata */}
        <Card>
          <CardHeader>
            <CardTitle>基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium text-muted-foreground">类型</p>
                <div className="mt-1">
                  <Badge variant={getTypeVariant(source.type)}>
                    {source.type}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">
                  知识块数
                </p>
                <p className="mt-1 text-sm">{source.chunk_count}</p>
              </div>
              <div className="col-span-2">
                <p className="text-sm font-medium text-muted-foreground">标题</p>
                <p className="mt-1 text-sm">
                  {source.title || (
                    <span className="text-muted-foreground">未命名来源</span>
                  )}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-sm font-medium text-muted-foreground">URL</p>
                <p className="mt-1 text-sm">
                  {source.url ? (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline"
                    >
                      {source.url}
                    </a>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </p>
              </div>
              <div className="col-span-2">
                <p className="text-sm font-medium text-muted-foreground">
                  文件路径
                </p>
                <p className="mt-1 text-sm font-mono">
                  {source.file_path || (
                    <span className="text-muted-foreground">—</span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">
                  访问时间
                </p>
                <p className="mt-1 text-sm">
                  {source.accessed_at ? (
                    new Date(source.accessed_at).toLocaleString("zh-CN")
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">
                  创建时间
                </p>
                <p className="mt-1 text-sm">
                  {new Date(source.created_at).toLocaleString("zh-CN")}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Associated Chunks */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>关联知识块</CardTitle>
              <Badge variant="secondary">{source.chunk_count}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {chunks.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无关联知识块</p>
            ) : (
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>内容预览</TableHead>
                      <TableHead>分类</TableHead>
                      <TableHead>绑定状态</TableHead>
                      <TableHead>桥梁</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {chunks.map((chunk) => (
                      <TableRow
                        key={chunk.id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/chunks/${chunk.id}`)}
                      >
                        <TableCell className="max-w-md truncate">
                          {chunk.content_preview}
                        </TableCell>
                        <TableCell>
                          {chunk.lvl1 || (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getBindingVariant(chunk.binding_status)}>
                            {getBindingLabel(chunk.binding_status)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {chunk.bridge_name || (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  )
}
