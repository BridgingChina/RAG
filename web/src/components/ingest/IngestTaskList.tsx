import { useEffect, useRef } from "react"
import { useNavigate } from "react-router"
import {
  Loader2,
  CheckCircle2,
  XCircle,
  PenLine,
  RotateCw,
  Play,
  Clock,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import type { IngestTaskItem, IngestTaskStatus } from "@/lib/types"
import { confirmIngestTask, deleteIngestTask } from "@/lib/api"

interface IngestTaskListProps {
  tasks: IngestTaskItem[]
  onRefresh: () => void
}

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

function isRunning(status: IngestTaskStatus): boolean {
  return ["uploading", "syncing", "parsing", "indexing"].includes(status)
}

function isQueued(status: IngestTaskStatus): boolean {
  return status === "queued" || status === "queued_for_indexing"
}

/** Tasks the UI should poll for updates on (includes queued — user is waiting). */
function shouldPoll(status: IngestTaskStatus): boolean {
  return isRunning(status) || isQueued(status)
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return ""
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

function TaskStatusBadge({ status }: { status: IngestTaskStatus }) {
  if (isQueued(status)) {
    // Waiting for the ingest scheduler to dispatch (issue #152).
    // Distinct from running (orange spinner) and failed (red X).
    return (
      <span className="inline-flex items-center gap-1 text-sm text-slate-500">
        <Clock className="h-3.5 w-3.5" />
        {STATUS_LABELS[status]}
      </span>
    )
  }
  if (isRunning(status)) {
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
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-sm text-red-600">
        <XCircle className="h-3.5 w-3.5" />
        {STATUS_LABELS[status]}
      </span>
    )
  }
  // deleted / any unknown — neutral display instead of silently rendering empty
  return (
    <span className="text-sm text-slate-400">
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

function TaskRow({ task, onRefresh }: { task: IngestTaskItem; onRefresh: () => void }) {
  const navigate = useNavigate()

  async function handleDelete() {
    if (!confirm("确定删除此任务？")) return
    try {
      await deleteIngestTask(task.id)
      onRefresh()
    } catch {
      // silent — task may already be deleted or in-progress
    }
  }

  async function handleConfirm() {
    try {
      await confirmIngestTask(task.id)
      onRefresh()
    } catch {
      // silent — status may have changed
    }
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100 last:border-b-0">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-slate-800 truncate">
            {task.file_name}
          </span>
          <TaskStatusBadge status={task.status} />
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-400">
          <span>{formatTime(task.created_at)}</span>
          {task.file_size && (
            <>
              <span>&middot;</span>
              <span>{formatSize(task.file_size)}</span>
            </>
          )}
          {task.chunk_count !== null && (
            <>
              <span>&middot;</span>
              <span>{task.chunk_count} 个知识块</span>
            </>
          )}
          {task.image_count > 0 && (
            <>
              <span>&middot;</span>
              <span>{task.image_count} 张图</span>
            </>
          )}
        </div>
        {task.status === "failed" && task.error_message && (
          <p className="text-xs text-red-500 mt-1 truncate">{task.error_message}</p>
        )}
      </div>

      <div className="flex items-center gap-2 ml-4 shrink-0">
        {task.status === "chunked" && task.source_id && (
          <>
            <Button
              size="sm"
              variant="outline"
              className="gap-1"
              onClick={() => navigate(`/sources/${task.source_id}/chunks/edit`)}
            >
              <PenLine className="h-3 w-3" />
              去校对
            </Button>
            <Button
              size="sm"
              className="gap-1"
              onClick={handleConfirm}
            >
              <Play className="h-3 w-3" />
              确认入库
            </Button>
          </>
        )}
        {task.status === "failed" && (
          <Button
            size="sm"
            variant="outline"
            onClick={handleDelete}
            className="gap-1 text-red-600 hover:text-red-700"
          >
            <RotateCw className="h-3 w-3" />
            删除
          </Button>
        )}
      </div>
    </div>
  )
}

export function IngestTaskList({ tasks, onRefresh }: IngestTaskListProps) {
  // Auto-poll when any task is running OR waiting in the scheduler queue
  // (so the UI updates when the scheduler picks up queued work — #152).
  const hasActiveTask = tasks.some((t) => shouldPoll(t.status))
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (hasActiveTask) {
      intervalRef.current = setInterval(onRefresh, 3000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [hasActiveTask, onRefresh])

  if (tasks.length === 0) {
    return (
      <div className="text-center text-sm text-slate-400 py-8">
        暂无入库任务
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white divide-y divide-slate-100">
      {tasks.map((task) => (
        <TaskRow key={task.id} task={task} onRefresh={onRefresh} />
      ))}
    </div>
  )
}
