import { useState, useEffect, useMemo } from "react"
import { useNavigate } from "react-router"
import {
  Plus,
  Loader2,
  CheckCircle2,
  XCircle,
  Search,
  RotateCw,
  PenLine,
  Trash2,
} from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { IngestPanel } from "@/components/ingest/IngestPanel"
import { FileUploadZone } from "@/components/ingest/FileUploadZone"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useApi } from "@/hooks/useApi"
import {
  fetchIngestTasks,
  confirmIngestTask,
  deleteIngestTask,
  retryIngestTask,
  batchDeleteIngestTasks,
} from "@/lib/api"
import type { IngestTaskItem, IngestTaskStatus } from "@/lib/types"

// --- Helper functions ---

const STATUS_LABELS: Record<IngestTaskStatus, string> = {
  uploading: "上传中",
  syncing: "同步中",
  parsing: "解析中",
  chunked: "待确认",
  indexing: "标识中",
  completed: "已完成",
  failed: "失败",
  deleted: "已删除",
}

function isInProgress(status: IngestTaskStatus): boolean {
  return ["uploading", "syncing", "parsing", "indexing"].includes(status)
}

function formatTime(isoStr: string): string {
  const d = new Date(isoStr)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return "刚刚"
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return d.toLocaleDateString("zh-CN")
}

// --- TaskStatusBadge ---

function TaskStatusBadge({ status }: { status: IngestTaskStatus }) {
  if (isInProgress(status)) {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-orange-600">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (status === "chunked") {
    return (
      <span className="text-sm font-medium text-blue-600">
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-green-600">
        <CheckCircle2 className="h-3.5 w-3.5" />
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (status === "deleted") {
    return (
      <span className="text-sm text-muted-foreground">
        {STATUS_LABELS[status]}
      </span>
    )
  }
  // failed
  return (
    <span className="inline-flex items-center gap-1 text-sm text-red-600">
      <XCircle className="h-3.5 w-3.5" />
      {STATUS_LABELS[status]}
    </span>
  )
}

// --- Main page component ---

export function Component() {
  const navigate = useNavigate()

  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [searchQuery, setSearchQuery] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [r2Available, setR2Available] = useState(true)
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false)

  // Search debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data, loading, error, refetch } = useApi(
    () => {
      const params: Record<string, unknown> = { page, page_size: 20 }
      if (debouncedSearch) params.file_name = debouncedSearch
      if (statusFilter === "deleted") {
        params.status = "deleted"
      } else if (!["all", "running"].includes(statusFilter)) {
        params.status = statusFilter
      }
      return fetchIngestTasks(params)
    },
    [page, statusFilter, debouncedSearch],
  )

  // R2 fallback detection — render-phase state adjustment (avoids setState-in-effect lint)
  if (r2Available && error?.includes("R2 storage is not configured")) {
    setR2Available(false)
  }

  // Auto-polling when tasks are in progress
  useEffect(() => {
    if (data?.items.some((t) => isInProgress(t.status))) {
      const interval = setInterval(refetch, 3000)
      return () => clearInterval(interval)
    }
  }, [data, refetch])

  // Client-side filtering for "running" tab
  const displayedTasks = useMemo(() => {
    if (!data) return []
    if (statusFilter === "running") {
      return data.items.filter((t) => isInProgress(t.status))
    }
    return data.items
  }, [data, statusFilter])

  const handleStatusChange = (value: string) => {
    setStatusFilter(value)
    setPage(1)
    setSelectedIds(new Set())
  }

  // Checkbox logic
  const selectableTasks = displayedTasks.filter((t) => !isInProgress(t.status))
  const allSelected =
    selectableTasks.length > 0 &&
    selectableTasks.every((t) => selectedIds.has(t.id))

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(selectableTasks.map((t) => t.id)))
    } else {
      setSelectedIds(new Set())
    }
  }

  const handleSelectRow = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  // Row action handlers
  async function handleConfirm(id: string) {
    try {
      await confirmIngestTask(id)
      refetch()
    } catch {
      // silent — backend error will surface on next poll
    }
  }

  async function handleRetry(id: string) {
    try {
      await retryIngestTask(id)
      refetch()
    } catch {
      // silent
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除此任务？")) return
    try {
      await deleteIngestTask(id)
      refetch()
    } catch {
      // silent
    }
  }

  async function handleBatchDelete() {
    if (!confirm(`确定删除 ${selectedIds.size} 个任务？`)) return
    try {
      await batchDeleteIngestTasks([...selectedIds])
      setSelectedIds(new Set())
      refetch()
    } catch {
      // silent
    }
  }

  // Upload dialog callback
  const handleTaskCreated = () => {
    setUploadDialogOpen(false)
    refetch()
  }

  // R2 fallback
  if (!r2Available) {
    return (
      <>
        <PageHeader title="入库管理" description="通过 Markdown 文本入库（R2 未配置）" />
        <main className="p-6">
          <IngestPanel />
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader title="入库管理" description="管理文档入库任务" />

      <main className="space-y-6 p-6">
        {/* Top bar */}
        <div className="flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="搜索文件名..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Button onClick={() => setUploadDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            新建任务
          </Button>
        </div>

        {/* Status filter tabs */}
        <Tabs value={statusFilter} onValueChange={handleStatusChange}>
          <TabsList>
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="running">进行中</TabsTrigger>
            <TabsTrigger value="chunked">待确认</TabsTrigger>
            <TabsTrigger value="completed">已完成</TabsTrigger>
            <TabsTrigger value="failed">失败</TabsTrigger>
            <TabsTrigger value="deleted">已删除</TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Batch delete bar */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-4 rounded-lg border bg-muted/50 px-4 py-2">
            <span className="text-sm">已选 {selectedIds.size} 项</span>
            <Button variant="destructive" size="sm" onClick={handleBatchDelete}>
              批量删除
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedIds(new Set())}
            >
              取消
            </Button>
          </div>
        )}

        {/* Content area — only show skeletons on first load, keep table visible during refetch */}
        {loading && !data ? (
          <div className="rounded-lg border">
            <div className="space-y-0">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="flex items-center gap-4 px-4 py-3 border-b last:border-0">
                  <Skeleton className="h-4 w-4 rounded" />
                  <Skeleton className="h-4 w-12" />
                  <Skeleton className="h-4 flex-1" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-24" />
                </div>
              ))}
            </div>
          </div>
        ) : error && r2Available ? (
          <div className="flex flex-col items-center gap-4 py-12 text-sm text-muted-foreground">
            <p>加载失败：{error}</p>
            <Button variant="outline" size="sm" onClick={refetch}>
              <RotateCw className="h-4 w-4 mr-1" />
              重试
            </Button>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">
                      <Checkbox
                        checked={allSelected}
                        onCheckedChange={(checked) =>
                          handleSelectAll(checked === true)
                        }
                        aria-label="全选"
                        disabled={selectableTasks.length === 0}
                      />
                    </TableHead>
                    <TableHead className="w-16">ID</TableHead>
                    <TableHead>文件名</TableHead>
                    <TableHead className="w-16">类型</TableHead>
                    <TableHead className="w-24">状态</TableHead>
                    <TableHead className="w-24">来源</TableHead>
                    <TableHead className="w-28">创建时间</TableHead>
                    <TableHead className="w-48 text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayedTasks.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={8}
                        className="py-12 text-center text-muted-foreground"
                      >
                        暂无任务
                      </TableCell>
                    </TableRow>
                  ) : (
                    displayedTasks.map((task) => (
                      <TaskRow
                        key={task.id}
                        task={task}
                        selected={selectedIds.has(task.id)}
                        onSelect={(checked) => handleSelectRow(task.id, checked)}
                        onConfirm={() => handleConfirm(task.id)}
                        onRetry={() => handleRetry(task.id)}
                        onDelete={() => handleDelete(task.id)}
                        onNavigate={() => navigate(`/ingest-tasks/${task.id}`)}
                        onNavigateEdit={() =>
                          navigate(`/sources/${task.source_id}/chunks/edit`)
                        }
                        onNavigateSource={(sourceId) =>
                          navigate(`/sources/${sourceId}`)
                        }
                      />
                    ))
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Pagination — hide on "running" tab where client-side filtering makes counts inaccurate */}
            {data && data.total_pages > 1 && statusFilter !== "running" && (
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  共 {data.total} 条，第 {page} / {data.total_pages} 页
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setPage((p) => Math.min(data.total_pages, p + 1))
                    }
                    disabled={page >= data.total_pages}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Upload dialog */}
      <Dialog open={uploadDialogOpen} onOpenChange={setUploadDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>新建入库任务</DialogTitle>
          </DialogHeader>
          <FileUploadZone
            onTaskCreated={handleTaskCreated}
            onError={(err) => {
              if (err.includes("R2 storage is not configured")) {
                setR2Available(false)
                setUploadDialogOpen(false)
              }
            }}
          />
        </DialogContent>
      </Dialog>
    </>
  )
}

// --- TaskRow sub-component ---

interface TaskRowProps {
  task: IngestTaskItem
  selected: boolean
  onSelect: (checked: boolean) => void
  onConfirm: () => void
  onRetry: () => void
  onDelete: () => void
  onNavigate: () => void
  onNavigateEdit: () => void
  onNavigateSource: (sourceId: string) => void
}

function TaskRow({
  task,
  selected,
  onSelect,
  onConfirm,
  onRetry,
  onDelete,
  onNavigate,
  onNavigateEdit,
  onNavigateSource,
}: TaskRowProps) {
  const running = isInProgress(task.status)

  return (
    <TableRow>
      <TableCell>
        <Checkbox
          checked={selected}
          onCheckedChange={(checked) => onSelect(checked === true)}
          disabled={running}
          aria-label={`选择任务 ${task.id}`}
        />
      </TableCell>
      <TableCell>
        <button
          className="text-sm font-mono text-muted-foreground hover:text-foreground hover:underline"
          onClick={onNavigate}
        >
          #{task.id}
        </button>
      </TableCell>
      <TableCell>
        <span className="text-sm font-medium truncate max-w-xs block">
          {task.file_name}
        </span>
      </TableCell>
      <TableCell>
        <span className="text-xs uppercase text-muted-foreground">
          {task.file_type}
        </span>
      </TableCell>
      <TableCell>
        <TaskStatusBadge status={task.status} />
      </TableCell>
      <TableCell>
        {task.source_id ? (
          <button
            className="text-sm text-blue-600 hover:underline"
            onClick={() => onNavigateSource(task.source_id!)}
          >
            #{task.source_id}
          </button>
        ) : (
          <span className="text-sm text-muted-foreground">--</span>
        )}
      </TableCell>
      <TableCell>
        <span className="text-sm text-muted-foreground">
          {formatTime(task.created_at)}
        </span>
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          {/* chunked: edit + confirm */}
          {task.status === "chunked" && task.source_id != null && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={onNavigateEdit}
            >
              <PenLine className="h-3.5 w-3.5 mr-1" />
              校对
            </Button>
          )}
          {task.status === "chunked" && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-blue-600 hover:text-blue-700"
              onClick={onConfirm}
            >
              确认入库
            </Button>
          )}

          {/* failed / deleted: retry */}
          {(task.status === "failed" ||
            task.status === "deleted") && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={onRetry}
            >
              <RotateCw className="h-3.5 w-3.5 mr-1" />
              重运行
            </Button>
          )}

          {/* delete: all non-running */}
          {!running && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-red-600 hover:text-red-700"
              onClick={onDelete}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}
