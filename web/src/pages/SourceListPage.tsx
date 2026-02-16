import { useState } from "react"
import { useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { useApi } from "@/hooks/useApi"
import { fetchSources } from "@/lib/api"

// Helper function for source type badge variant
function getTypeVariant(type: string) {
  if (type === "pdf") return "default"
  if (type === "web") return "secondary"
  if (type === "note") return "outline"
  return "secondary"
}

export function Component() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [typeFilter, setTypeFilter] = useState<string>("all")

  const { data, loading, error, refetch } = useApi(
    () =>
      fetchSources({
        page,
        page_size: 20,
        q: search || undefined,
        type: typeFilter === "all" ? undefined : typeFilter,
      }),
    [page, search, typeFilter],
  )

  // Reset page when search or filter changes
  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  const handleTypeFilterChange = (value: string) => {
    setTypeFilter(value)
    setPage(1)
  }

  if (loading) {
    return (
      <>
        <PageHeader title="来源管理" description="浏览和查看来源信息" />
        <main className="space-y-6 p-6">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-96 w-full" />
        </main>
      </>
    )
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="来源管理" description="浏览和查看来源信息" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">
              {error || "加载失败"}
            </p>
            <Button onClick={refetch} variant="outline" size="sm">
              重试
            </Button>
          </div>
        </main>
      </>
    )
  }

  const { items, total_pages } = data
  const hasNext = total_pages > 0 && page < total_pages
  const hasPrev = page > 1

  return (
    <>
      <PageHeader title="来源管理" description="浏览和查看来源信息" />

      <main className="space-y-6 p-6">
        {/* Search and Filters */}
        <div className="flex items-center gap-4">
          <Input
            placeholder="搜索来源..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="max-w-sm"
          />
          <Select value={typeFilter} onValueChange={handleTypeFilterChange}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="选择类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="pdf">PDF</SelectItem>
              <SelectItem value="web">网页</SelectItem>
              <SelectItem value="note">笔记</SelectItem>
              <SelectItem value="document">文档</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">暂无来源数据</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>类型</TableHead>
                    <TableHead>标题</TableHead>
                    <TableHead>知识块数</TableHead>
                    <TableHead>创建时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((source) => (
                    <TableRow
                      key={source.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/sources/${source.id}`)}
                    >
                      <TableCell>
                        <Badge variant={getTypeVariant(source.type)}>
                          {source.type}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">
                        {source.title || (
                          <span className="text-muted-foreground">
                            未命名来源
                          </span>
                        )}
                      </TableCell>
                      <TableCell>{source.chunk_count}</TableCell>
                      <TableCell>
                        {new Date(source.created_at).toLocaleDateString(
                          "zh-CN",
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            {total_pages > 0 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  第 {page} / {total_pages} 页
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page - 1)}
                    disabled={!hasPrev}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page + 1)}
                    disabled={!hasNext}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </>
  )
}
