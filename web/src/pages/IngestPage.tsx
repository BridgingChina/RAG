import { useCallback, useState, useEffect } from "react"
import { PageHeader } from "@/components/layout/PageHeader"
import { FileUploadZone } from "@/components/ingest/FileUploadZone"
import { IngestTaskList } from "@/components/ingest/IngestTaskList"
import { IngestPanel } from "@/components/ingest/IngestPanel"
import { fetchIngestTasks } from "@/lib/api"
import type { IngestTaskItem } from "@/lib/types"

export function Component() {
  const [tasks, setTasks] = useState<IngestTaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [r2Available, setR2Available] = useState(true)

  const loadTasks = useCallback(async () => {
    try {
      const res = await fetchIngestTasks({ page: 1, page_size: 50 })
      setTasks(res.items)
    } catch {
      // If tasks endpoint works but returns empty, R2 is configured.
      // If it fails, still show upload zone — the 503 will surface on presign.
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTasks()
  }, [loadTasks])

  const handleTaskCreated = (task: IngestTaskItem) => {
    setTasks((prev) => [task, ...prev])
  }

  const handleUploadError = (error: string) => {
    if (error.includes("R2 storage is not configured")) {
      setR2Available(false)
    }
  }

  if (!r2Available) {
    return (
      <>
        <PageHeader title="入库" description="通过 Markdown 文本入库（R2 未配置）" />
        <main className="p-6">
          <IngestPanel />
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader title="入库" description="上传文档到知识库" />
      <main className="p-6 space-y-6">
        <FileUploadZone
          onTaskCreated={handleTaskCreated}
          onError={handleUploadError}
        />

        <div>
          <h2 className="text-sm font-medium text-slate-700 mb-3">入库任务</h2>
          {loading ? (
            <div className="text-center text-sm text-slate-400 py-8">加载中...</div>
          ) : (
            <IngestTaskList tasks={tasks} onRefresh={loadTasks} />
          )}
        </div>
      </main>
    </>
  )
}
