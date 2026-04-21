import { useMemo, useState } from "react"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ProviderCard } from "./ProviderCard"
import { ProviderFormDialog } from "./ProviderFormDialog"
import { ProviderDeleteDialog } from "./ProviderDeleteDialog"
import { useLLMProviders } from "@/hooks/useLLMProviders"
import { useLLMTasks } from "@/hooks/useLLMTasks"
import type { ProviderPublic } from "@/lib/types/llm"

export function ProvidersTab() {
  const providers = useLLMProviders()
  const tasks = useLLMTasks()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<ProviderPublic | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ProviderPublic | null>(null)

  // Per-provider count + task-key list — computed from the task routes so
  // delete dialogs can show exactly which tasks need to be re-pointed.
  const { countByProvider, taskKeysByProvider } = useMemo(() => {
    const countMap = new Map<string, number>()
    const keysMap = new Map<string, string[]>()
    for (const r of tasks.data ?? []) {
      countMap.set(r.provider_id, (countMap.get(r.provider_id) ?? 0) + 1)
      const existing = keysMap.get(r.provider_id) ?? []
      existing.push(r.task_key)
      keysMap.set(r.provider_id, existing)
    }
    return { countByProvider: countMap, taskKeysByProvider: keysMap }
  }, [tasks.data])

  const handleCreate = () => {
    setEditing(null)
    setFormOpen(true)
  }

  const handleEdit = (p: ProviderPublic) => {
    setEditing(p)
    setFormOpen(true)
  }

  const handleSaved = () => {
    providers.refetch()
  }

  const handleDeleted = () => {
    providers.refetch()
    tasks.refetch()
  }

  if (providers.loading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-32 w-full" />
        ))}
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

  const rows = providers.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end">
        <Button onClick={handleCreate}>+ 新增供应商</Button>
      </div>

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-sm text-muted-foreground">
            暂未配置任何供应商。点击「+ 新增供应商」开始。
          </p>
        </div>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {rows.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              inUseCount={countByProvider.get(p.id) ?? 0}
              onRefresh={providers.refetch}
              onEdit={() => handleEdit(p)}
              onDelete={() => setDeleteTarget(p)}
            />
          ))}
        </div>
      )}

      <ProviderFormDialog
        open={formOpen}
        initial={editing}
        onOpenChange={setFormOpen}
        onSaved={handleSaved}
      />

      <ProviderDeleteDialog
        open={!!deleteTarget}
        provider={deleteTarget}
        inUseTaskKeys={
          deleteTarget
            ? taskKeysByProvider.get(deleteTarget.id) ?? []
            : []
        }
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        onDeleted={handleDeleted}
      />
    </div>
  )
}
