import { useState } from "react"
import { useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Pagination } from "@/components/Pagination"
import { useApi } from "@/hooks/useApi"
import { fetchBridges } from "@/lib/api"

export function Component() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")

  const { data, loading, error, refetch } = useApi(
    () =>
      fetchBridges({
        page,
        page_size: 20,
        q: search || undefined,
      }),
    [page, search],
  )

  // Reset page when search changes
  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  if (loading) {
    return (
      <>
        <PageHeader title="桥梁管理" description="浏览和管理桥梁档案">
          <Button disabled>新建桥梁</Button>
        </PageHeader>
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
        <PageHeader title="桥梁管理" description="浏览和管理桥梁档案">
          <Button onClick={() => navigate("/bridges/new")}>新建桥梁</Button>
        </PageHeader>
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

  return (
    <>
      <PageHeader title="桥梁管理" description="浏览和管理桥梁档案">
        <Button onClick={() => navigate("/bridges/new")}>新建桥梁</Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {/* Search */}
        <div className="flex items-center gap-4">
          <Input
            placeholder="搜索桥梁..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
            className="max-w-sm"
          />
        </div>

        {/* Table */}
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">暂无桥梁数据</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead>
                    <TableHead>桥型</TableHead>
                    <TableHead>材料</TableHead>
                    <TableHead>年代</TableHead>
                    <TableHead>知识块数</TableHead>
                    <TableHead>位置</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((bridge) => (
                    <TableRow
                      key={bridge.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/bridges/${bridge.id}`)}
                    >
                      <TableCell className="font-medium">
                        {bridge.name}
                      </TableCell>
                      <TableCell>
                        {bridge.bridge_type || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {bridge.material || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {bridge.era || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>{bridge.chunk_count}</TableCell>
                      <TableCell>
                        {bridge.region || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <Pagination page={page} totalPages={total_pages} onPageChange={setPage} />
          </>
        )}
      </main>
    </>
  )
}
