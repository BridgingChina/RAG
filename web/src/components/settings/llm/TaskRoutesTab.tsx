import { useEffect, useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { TaskRouteCard } from "./TaskRouteCard"
import { useLLMProviders } from "@/hooks/useLLMProviders"
import { useLLMTasks } from "@/hooks/useLLMTasks"
import {
  batchUpdateTaskRoutes,
  invalidateRouteCache,
} from "@/lib/api/llm"
import type { TaskRoutePublic } from "@/lib/types/llm"

interface DraftEntry {
  provider_id: string
  model_id: string
}

function buildDrafts(routes: TaskRoutePublic[]): Record<string, DraftEntry> {
  const out: Record<string, DraftEntry> = {}
  for (const r of routes) {
    out[r.task_key] = { provider_id: r.provider_id, model_id: r.model_id }
  }
  return out
}

export function TaskRoutesTab() {
  const tasks = useLLMTasks()
  const providers = useLLMProviders()
  const [drafts, setDrafts] = useState<Record<string, DraftEntry>>({})
  const [saving, setSaving] = useState(false)
  const [invalidating, setInvalidating] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [actionOk, setActionOk] = useState<string | null>(null)

  // Hydrate drafts from server response.
  useEffect(() => {
    if (tasks.data) {
      setDrafts(buildDrafts(tasks.data))
    }
  }, [tasks.data])

  const dirtyTaskKeys = useMemo(() => {
    if (!tasks.data) return new Set<string>()
    const dirty = new Set<string>()
    for (const r of tasks.data) {
      const d = drafts[r.task_key]
      if (!d) continue
      if (d.provider_id !== r.provider_id || d.model_id !== r.model_id) {
        dirty.add(r.task_key)
      }
    }
    return dirty
  }, [tasks.data, drafts])

  const hasDirty = dirtyTaskKeys.size > 0

  const handleChange = (
    taskKey: string,
    providerId: string,
    modelId: string,
  ) => {
    setActionError(null)
    setActionOk(null)
    setDrafts((prev) => ({
      ...prev,
      [taskKey]: { provider_id: providerId, model_id: modelId },
    }))
  }

  const handleSaveAll = async () => {
    if (!tasks.data || !hasDirty) return
    // Validate all dirty rows carry a model_id (provider_id is required
    // too — the <Select> will never let it be empty in practice).
    const updates = Array.from(dirtyTaskKeys).map((taskKey) => {
      const d = drafts[taskKey]
      return { task_key: taskKey, provider_id: d.provider_id, model_id: d.model_id }
    })
    const missing = updates.filter((u) => !u.model_id || !u.provider_id)
    if (missing.length > 0) {
      setActionError(
        `以下任务未选择完整：${missing.map((u) => u.task_key).join(", ")}`,
      )
      return
    }

    setSaving(true)
    setActionError(null)
    setActionOk(null)
    try {
      await batchUpdateTaskRoutes({ updates })
      setActionOk(`已保存 ${updates.length} 条路由`)
      tasks.refetch()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleInvalidate = async () => {
    setInvalidating(true)
    setActionError(null)
    setActionOk(null)
    try {
      await invalidateRouteCache()
      setActionOk("已清除路由缓存")
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setInvalidating(false)
    }
  }

  if (tasks.loading || providers.loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2, 3, 4, 5, 6].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    )
  }

  if (tasks.error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
        <p className="mb-4 text-sm text-destructive">{tasks.error}</p>
        <Button onClick={tasks.refetch} variant="outline" size="sm">
          重试
        </Button>
      </div>
    )
  }

  if (providers.error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
        <p className="mb-4 text-sm text-destructive">{providers.error}</p>
        <Button onClick={providers.refetch} variant="outline" size="sm">
          重试
        </Button>
      </div>
    )
  }

  const taskList = tasks.data ?? []
  const providerList = providers.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={handleSaveAll} disabled={!hasDirty || saving}>
          {saving ? "保存中..." : "保存全部"}
          {hasDirty && !saving && (
            <span className="ml-1 text-xs opacity-75">
              ({dirtyTaskKeys.size})
            </span>
          )}
        </Button>
        <Button
          variant="outline"
          onClick={handleInvalidate}
          disabled={invalidating}
        >
          {invalidating ? "清除中..." : "强制清缓存"}
        </Button>
        {actionOk && (
          <span className="text-sm text-emerald-600">{actionOk}</span>
        )}
        {actionError && (
          <span className="text-sm text-destructive">{actionError}</span>
        )}
      </div>

      {taskList.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">
            暂无任务路由（请先运行 schema v13 迁移）
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {taskList.map((route) => {
            const d = drafts[route.task_key] ?? {
              provider_id: route.provider_id,
              model_id: route.model_id,
            }
            return (
              <TaskRouteCard
                key={route.task_key}
                route={route}
                providers={providerList}
                selectedProviderId={d.provider_id}
                selectedModelId={d.model_id}
                dirty={dirtyTaskKeys.has(route.task_key)}
                onChange={handleChange}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
