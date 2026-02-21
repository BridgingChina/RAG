import { useCallback, useState, useEffect } from "react"
import { PageHeader } from "@/components/layout/PageHeader"
import { FileUploadZone } from "@/components/ingest/FileUploadZone"
import { IngestTaskList } from "@/components/ingest/IngestTaskList"
import { fetchIngestTasks } from "@/lib/api"
import type { IngestTaskItem } from "@/lib/types"

export function Component() {
  const [tasks, setTasks] = useState<IngestTaskItem[]>([])
  const [loading, setLoading] = useState(true)

  const loadTasks = useCallback(async () => {
    try {
      const res = await fetchIngestTasks({ page: 1, page_size: 50 })
      setTasks(res.items)
    } catch {
      // silent — page still functional
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

  return (
    <>
      <PageHeader title="入库" description="上传文档到知识库" />
      <main className="p-6 space-y-6">
        <FileUploadZone onTaskCreated={handleTaskCreated} />

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
