import { useState, useEffect } from "react"
import { useParams, useNavigate, Link } from "react-router"
import {
  ArrowLeft,
  Download,
  Loader2,
  CheckCircle2,
  XCircle,
  RotateCw,
  PenLine,
  Trash2,
} from "lucide-react"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/useApi"
import {
  fetchIngestTask,
  fetchAuditLogs,
  confirmIngestTask,
  deleteIngestTask,
  retryIngestTask,
  getIngestTaskDownloadUrl,
  RetryRejectedError,
} from "@/lib/api"
import type { IngestTaskStatus, AuditLogItem } from "@/lib/types"

// --- Helper functions (same as IngestPage) ---

const STATUS_LABELS: Record<IngestTaskStatus, string> = {
  uploading: "上传中",
  queued: "排队中",
  syncing: "同步中",
  parsing: "解析中",
  chunked: "待确认",
  queued_for_indexing: "排队中 (待标识)",
  indexing: "标识中",
  completed: "已完成",
  failed: "失败",
  deleted: "已删除",
}

function isInProgress(status: IngestTaskStatus): boolean {
  // Includes scheduler-queued states (#152) so polling continues while
  // tasks wait for the global concurrency slot.
  return [
    "uploading",
    "queued",
    "syncing",
    "parsing",
    "queued_for_indexing",
    "indexing",
  ].includes(status)
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return "--"
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
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

function formatAbsoluteTime(isoStr: string): string {
  const d = new Date(isoStr)
  return d.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

// --- TaskStatusBadge ---

interface TaskStatusBadgeProps {
  status: IngestTaskStatus
  chunksIndexed?: number | null
  chunkCount?: number | null
}

function TaskStatusBadge({ status, chunksIndexed, chunkCount }: TaskStatusBadgeProps) {
  if (isInProgress(status)) {
    const showProgress =
      status === "indexing" &&
      typeof chunkCount === "number" &&
      chunkCount > 0 &&
      typeof chunksIndexed === "number"
    return (
      <span className="inline-flex items-center gap-1 text-sm text-[var(--yellow-hemp)]">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {STATUS_LABELS[status]}
        {showProgress && (
          <span className="ml-1 font-mono text-xs text-[var(--yellow-hemp)]/80">
            {chunksIndexed}/{chunkCount}
          </span>
        )}
      </span>
    )
  }
  if (status === "chunked") {
    return (
      <span className="text-sm font-medium text-[var(--songci-celadon)]">
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (status === "completed") {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-[var(--songci-celadon-deep)]">
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
    <span className="inline-flex items-center gap-1 text-sm text-destructive">
      <XCircle className="h-3.5 w-3.5" />
      {STATUS_LABELS[status]}
    </span>
  )
}

// --- Audit action label map ---

const AUDIT_ACTION_LABELS: Record<string, string> = {
  ingest: "创建任务",
  confirm_ingest: "确认入库",
  delete: "删除",
  retry_ingest: "重运行",
  ingest_parse_start: "开始解析",
  ingest_parse_done: "解析完成",
  ingest_index_done: "索引完成",
  ingest_failed: "任务失败",
}

function auditActionLabel(action: string): string {
  return AUDIT_ACTION_LABELS[action] ?? action
}

// --- AuditTimeline ---

function AuditTimeline({ entries }: { entries: AuditLogItem[] }) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">暂无审计记录</p>
    )
  }

  return (
    <ol className="relative border-l border-border ml-2 space-y-6">
      {entries.map((entry) => (
        <li key={entry.id} className="ml-4">
          {/* Dot on the line */}
          <span className="absolute -left-[5px] mt-1 h-2.5 w-2.5 rounded-full border border-background bg-border" />

          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium">
                {auditActionLabel(entry.action)}
              </span>
              {entry.user_id && (
                <span className="text-xs text-muted-foreground font-mono">
                  by {entry.user_id.slice(0, 8)}
                </span>
              )}
            </div>
            <span className="text-xs text-muted-foreground">
              {formatAbsoluteTime(entry.created_at)}
            </span>
            {entry.detail && Object.keys(entry.detail).length > 0 && (
              <p className="text-xs text-muted-foreground mt-0.5 font-mono break-all">
                {JSON.stringify(entry.detail)}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  )
}

// --- Main page component ---

export function Component() {
  const { id: taskId } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const {
    data: task,
    loading,
    error,
    refetch,
  } = useApi(() => fetchIngestTask(taskId!), [taskId])

  const { data: auditData, loading: auditLoading } = useApi(
    () =>
      fetchAuditLogs({
        resource_type: "ingest_task",
        resource_id: taskId!,
        page_size: 50,
      }),
    [taskId],
  )

  // Auto-polling when task is in progress
  useEffect(() => {
    if (task && isInProgress(task.status)) {
      const interval = setInterval(refetch, 3000)
      return () => clearInterval(interval)
    }
  }, [task, refetch])

  // --- Action state ---
  const [actionError, setActionError] = useState<string | null>(null)

  // --- Action handlers ---

  async function handleConfirm() {
    if (!task) return
    setActionError(null)
    try {
      await confirmIngestTask(task.id)
      refetch()
    } catch (e) {
      setActionError(`确认失败：${e instanceof Error ? e.message : "未知错误"}`)
    }
  }

  async function handleRetry() {
    if (!task) return
    setActionError(null)
    try {
      await retryIngestTask(task.id)
      refetch()
    } catch (e) {
      // Show the structured backend message directly when it's a retry
      // rejection (cooldown / running / queued). Generic errors get the
      // legacy "重试失败：" prefix.
      if (e instanceof RetryRejectedError) {
        setActionError(e.message)
      } else {
        setActionError(`重试失败：${e instanceof Error ? e.message : "未知错误"}`)
      }
      refetch()
    }
  }

  async function handleDelete() {
    if (!task) return
    if (!confirm("确定删除此任务？")) return
    setActionError(null)
    try {
      await deleteIngestTask(task.id)
      navigate("/ingest")
    } catch (e) {
      setActionError(`删除失败：${e instanceof Error ? e.message : "未知错误"}`)
    }
  }

  async function handleDownload(type: "raw" | "parsed") {
    setActionError(null)
    try {
      const res = await getIngestTaskDownloadUrl(taskId!, type)
      window.open(res.url, "_blank")
    } catch (e) {
      setActionError(`下载失败：${e instanceof Error ? e.message : "未知错误"}`)
    }
  }

  // --- Render ---

  const pageTitle = task ? `任务 #${task.id}` : `任务 #${taskId ?? ""}`
  const pageDescription = task?.file_name ?? ""

  return (
    <>
      <PageHeader title={pageTitle} description={pageDescription}>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/ingest")}
          className="gap-1"
        >
          <ArrowLeft className="h-4 w-4" />
          返回列表
        </Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {/* Action error banner */}
        {actionError && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {actionError}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && !task && (
          <div className="space-y-6">
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="grid grid-cols-2 gap-4">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="flex flex-col gap-1">
                    <Skeleton className="h-3 w-16" />
                    <Skeleton className="h-4 w-40" />
                  </div>
                ))}
              </div>
            </div>
            <Skeleton className="h-9 w-64" />
            <div className="rounded-lg border border-border bg-card p-6">
              <Skeleton className="h-32 w-full" />
            </div>
          </div>
        )}

        {/* Error state */}
        {error && !task && (
          <div className="flex flex-col items-center gap-4 py-12 text-sm text-muted-foreground">
            <p>加载失败：{error}</p>
            <Button variant="outline" size="sm" onClick={refetch}>
              <RotateCw className="h-4 w-4 mr-1" />
              重试
            </Button>
          </div>
        )}

        {task && (
          <>
            {/* Info card */}
            <div className="rounded-lg border border-border bg-card p-6">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {/* 文件名 */}
                <div>
                  <dt className="text-xs text-muted-foreground">文件名</dt>
                  <dd className="mt-0.5 text-sm font-medium break-all">
                    {task.file_name}
                  </dd>
                </div>

                {/* 文件类型 */}
                <div>
                  <dt className="text-xs text-muted-foreground">文件类型</dt>
                  <dd className="mt-0.5 text-sm font-mono uppercase">
                    {task.file_type}
                  </dd>
                </div>

                {/* 文件大小 */}
                <div>
                  <dt className="text-xs text-muted-foreground">文件大小</dt>
                  <dd className="mt-0.5 text-sm">{formatSize(task.file_size)}</dd>
                </div>

                {/* 状态 */}
                <div>
                  <dt className="text-xs text-muted-foreground">状态</dt>
                  <dd className="mt-0.5">
                    <TaskStatusBadge
                      status={task.status}
                      chunksIndexed={task.chunks_indexed}
                      chunkCount={task.chunk_count}
                    />
                  </dd>
                </div>

                {/* 关联来源 */}
                <div>
                  <dt className="text-xs text-muted-foreground">关联来源</dt>
                  <dd className="mt-0.5 text-sm">
                    {task.source_id ? (
                      <Link
                        to={`/sources/${task.source_id}`}
                        className="text-[var(--songci-celadon)] hover:underline"
                      >
                        #{task.source_id}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground">--</span>
                    )}
                  </dd>
                </div>

                {/* 创建时间 */}
                <div>
                  <dt className="text-xs text-muted-foreground">创建时间</dt>
                  <dd className="mt-0.5 text-sm text-muted-foreground">
                    {formatTime(task.created_at)}
                  </dd>
                </div>

                {/* 更新时间 */}
                <div>
                  <dt className="text-xs text-muted-foreground">更新时间</dt>
                  <dd className="mt-0.5 text-sm text-muted-foreground">
                    {formatTime(task.updated_at)}
                  </dd>
                </div>

                {/* 错误信息 — only when present */}
                {task.error_message && (
                  <div className="sm:col-span-2">
                    <dt className="text-xs text-muted-foreground">错误信息</dt>
                    <dd className="mt-0.5 text-sm text-destructive break-all">
                      {task.error_message}
                    </dd>
                  </div>
                )}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex flex-wrap items-center gap-2">
              {/* chunked: edit + confirm */}
              {task.status === "chunked" && task.source_id != null && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    navigate(`/sources/${task.source_id}/chunks/edit`)
                  }
                >
                  <PenLine className="h-4 w-4 mr-1" />
                  校对
                </Button>
              )}
              {task.status === "chunked" && (
                <Button
                  size="sm"
                  onClick={handleConfirm}
                >
                  确认入库
                </Button>
              )}

              {/* failed / deleted: retry */}
              {(task.status === "failed" ||
                task.status === "deleted") && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRetry}
                >
                  <RotateCw className="h-4 w-4 mr-1" />
                  重运行
                </Button>
              )}

              {/* delete: all non-running */}
              {!isInProgress(task.status) && (
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive/80 border-destructive/30 hover:border-destructive/50"
                  onClick={handleDelete}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  删除
                </Button>
              )}
            </div>

            {/* File download section */}
            <div className="rounded-lg border border-border bg-card p-6">
              <h2 className="text-sm font-medium mb-4">文件下载</h2>
              <div className="flex flex-wrap gap-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownload("raw")}
                >
                  <Download className="h-4 w-4 mr-1" />
                  下载原始文件
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={
                    task.status === "uploading" ||
                    task.status === "queued" ||
                    task.status === "syncing"
                  }
                  onClick={() => handleDownload("parsed")}
                >
                  <Download className="h-4 w-4 mr-1" />
                  下载解析结果
                </Button>
              </div>
            </div>

            {/* Audit log timeline */}
            <div className="rounded-lg border border-border bg-card p-6">
              <h2 className="text-sm font-medium mb-4">操作历史</h2>
              {auditLoading && !auditData ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="flex flex-col gap-1 ml-4">
                      <Skeleton className="h-4 w-32" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  ))}
                </div>
              ) : auditData ? (
                <AuditTimeline entries={auditData.items} />
              ) : (
                <p className="text-sm text-muted-foreground">审计记录加载失败</p>
              )}
            </div>
          </>
        )}
      </main>
    </>
  )
}
