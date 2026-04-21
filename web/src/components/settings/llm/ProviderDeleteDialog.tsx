import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { deleteProvider } from "@/lib/api/llm"
import type { ProviderPublic } from "@/lib/types/llm"

interface ProviderDeleteDialogProps {
  open: boolean
  provider: ProviderPublic | null
  /** Task keys currently routed to this provider (if any). */
  inUseTaskKeys: string[]
  onOpenChange: (open: boolean) => void
  onDeleted: () => void
}

export function ProviderDeleteDialog({
  open,
  provider,
  inUseTaskKeys,
  onOpenChange,
  onDeleted,
}: ProviderDeleteDialogProps) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const blocked = inUseTaskKeys.length > 0

  async function handleConfirm() {
    if (!provider || blocked) return
    setBusy(true)
    setError(null)
    try {
      await deleteProvider(provider.id)
      onDeleted()
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>删除供应商</DialogTitle>
          <DialogDescription>
            {provider ? (
              <>
                将删除「{provider.name}」。此操作不可逆。
              </>
            ) : null}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {blocked ? (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm">
              <p className="font-medium text-destructive">
                当前有 {inUseTaskKeys.length} 个任务路由指向此供应商，
                请先在「任务路由」页面调整后再删除。
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 font-mono text-xs text-destructive">
                {inUseTaskKeys.map((k) => (
                  <li key={k}>{k}</li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-muted-foreground">
                Please change routes first.
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              未被任何任务路由引用，可以安全删除。
            </p>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={busy}
          >
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={blocked || busy}
          >
            {busy ? "删除中..." : "删除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
