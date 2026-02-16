import { useState } from "react"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { useApi } from "@/hooks/useApi"
import { fetchAuditLogs } from "@/lib/api"

const NONE = "__all__"

const ACTION_OPTIONS = [
  { value: NONE, label: "全部操作" },
  { value: "login", label: "登录" },
  { value: "login_failure", label: "登录失败" },
  { value: "create", label: "创建" },
  { value: "update", label: "更新" },
  { value: "delete", label: "删除" },
  { value: "merge", label: "合并" },
  { value: "ingest", label: "入库" },
  { value: "batch_update", label: "批量更新" },
  { value: "change_password", label: "改密码" },
]

const RESOURCE_OPTIONS = [
  { value: NONE, label: "全部资源" },
  { value: "auth", label: "认证" },
  { value: "bridge", label: "桥梁" },
  { value: "chunk", label: "知识块" },
  { value: "source", label: "来源" },
  { value: "taxonomy", label: "分类" },
  { value: "settings", label: "设置" },
]

export function Component() {
  const [page, setPage] = useState(1)
  const [actionFilter, setActionFilter] = useState(NONE)
  const [resourceFilter, setResourceFilter] = useState(NONE)

  const { data, loading, error, refetch } = useApi(
    () =>
      fetchAuditLogs({
        page,
        page_size: 20,
        action: actionFilter === NONE ? undefined : actionFilter,
        resource_type: resourceFilter === NONE ? undefined : resourceFilter,
      }),
    [page, actionFilter, resourceFilter],
  )

  const handleFilterChange = (setter: (v: string) => void) => (value: string) => {
    setter(value)
    setPage(1)
  }

  if (loading) {
    return (
      <>
        <PageHeader title="审计日志" description="查看系统操作记录" />
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
        <PageHeader title="审计日志" description="查看系统操作记录" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{error || "加载失败"}</p>
            <Button onClick={refetch} variant="outline" size="sm">重试</Button>
          </div>
        </main>
      </>
    )
  }

  const { items, total_pages } = data

  return (
    <>
      <PageHeader title="审计日志" description="查看系统操作记录" />
      <main className="space-y-6 p-6">
        {/* Filters */}
        <div className="flex items-center gap-4">
          <Select value={actionFilter} onValueChange={handleFilterChange(setActionFilter)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ACTION_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={resourceFilter} onValueChange={handleFilterChange(setResourceFilter)}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RESOURCE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">暂无审计记录</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>时间</TableHead>
                    <TableHead>用户</TableHead>
                    <TableHead>操作</TableHead>
                    <TableHead>资源类型</TableHead>
                    <TableHead>资源 ID</TableHead>
                    <TableHead>IP</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((log) => (
                    <TableRow key={log.id}>
                      <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString("zh-CN")}
                      </TableCell>
                      <TableCell>{log.username || "-"}</TableCell>
                      <TableCell>
                        <Badge variant={log.action === "login_failure" ? "destructive" : "secondary"}>
                          {log.action}
                        </Badge>
                      </TableCell>
                      <TableCell>{log.resource_type}</TableCell>
                      <TableCell className="font-mono text-xs">{log.resource_id || "-"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{log.ip_address || "-"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {/* Pagination */}
            {total_pages > 0 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">第 {page} / {total_pages} 页</p>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => setPage(page - 1)} disabled={page <= 1}>上一页</Button>
                  <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={page >= total_pages}>下一页</Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </>
  )
}
