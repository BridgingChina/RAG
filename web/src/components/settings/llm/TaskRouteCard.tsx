import { Card, CardContent } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { ModelPicker } from "./ModelPicker"
import type { ProviderPublic, TaskRoutePublic } from "@/lib/types/llm"

interface TaskRouteCardProps {
  route: TaskRoutePublic
  providers: ProviderPublic[]
  /** Current selection (may equal the server route, or a pending local edit). */
  selectedProviderId: string
  selectedModelId: string
  /** True when the current selection differs from the server-side value. */
  dirty: boolean
  onChange: (taskKey: string, providerId: string, modelId: string) => void
}

export function TaskRouteCard({
  route,
  providers,
  selectedProviderId,
  selectedModelId,
  dirty,
  onChange,
}: TaskRouteCardProps) {
  // Only enabled providers can receive routes (backend enforces this on
  // save; hide them here too so the admin doesn't pick a route that
  // immediately 422s).
  const enabledProviders = providers.filter((p) => p.enabled)

  const handleProviderChange = (nextProviderId: string) => {
    // Provider changed — clear the model id so the admin re-picks.
    // Writing an empty string keeps Radix Select controlled; the ModelPicker
    // falls back to the placeholder.
    if (nextProviderId !== selectedProviderId) {
      onChange(route.task_key, nextProviderId, "")
    }
  }

  const handleModelChange = (nextModelId: string) => {
    onChange(route.task_key, selectedProviderId, nextModelId)
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="font-mono text-sm font-semibold">
                {route.task_key}
              </h3>
              {dirty && (
                <span
                  title="未保存"
                  className="inline-block h-2 w-2 rounded-full bg-[var(--yellow-hemp)]"
                />
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {route.description || "—"}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              供应商
            </label>
            <Select
              value={selectedProviderId || undefined}
              onValueChange={handleProviderChange}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="选择供应商" />
              </SelectTrigger>
              <SelectContent>
                {enabledProviders.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">
              模型
            </label>
            <ModelPicker
              providerId={selectedProviderId || null}
              value={selectedModelId || null}
              onChange={handleModelChange}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
