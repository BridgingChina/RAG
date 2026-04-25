import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { reviewTranslation } from "@/lib/api"
import type { TranslationReviewItem } from "@/lib/types"

interface Props {
  item: TranslationReviewItem | null
  onClose: () => void
  onSaved: () => void
}

export function TranslationReviewDialog({ item, onClose, onSaved }: Props) {
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (item) {
      setDraft(item.reviewed_translation ?? item.ai_translation ?? "")
      setError(null)
    }
  }, [item])

  if (!item) return null

  const aiText = item.ai_translation ?? ""
  const edited = draft.trim() !== aiText.trim()

  const callAction = async (
    action: "approve" | "edit" | "reject",
    text?: string,
  ) => {
    if (!item) return
    setBusy(true)
    setError(null)
    try {
      await reviewTranslation(item.id, { action, text })
      onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleApprove = () => {
    // Approve-as-is = approve action; approve-after-edit = edit action (writes draft).
    if (edited && draft.trim()) {
      void callAction("edit", draft.trim())
    } else {
      void callAction("approve")
    }
  }

  const handleReject = () => {
    void callAction("reject")
  }

  return (
    <Dialog open={!!item} onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>翻译审校</DialogTitle>
          <DialogDescription>
            <span className="font-mono text-xs">{item.table_name}.{item.field_name}</span>
            <span className="mx-2">·</span>
            <Badge variant="outline">{item.status}</Badge>
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              中文原文
            </label>
            <div className="rounded-md border bg-muted/30 p-3 text-sm leading-relaxed whitespace-pre-wrap">
              {item.source_text}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              英文译文（可编辑）
            </label>
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={8}
              placeholder="AI 尚未生成译文，可手动输入"
              disabled={busy}
            />
            {aiText && edited && (
              <p className="mt-1 text-xs text-[var(--yellow-hemp)]">
                已修改 AI 原译文；点击"通过"将以编辑后版本入库
              </p>
            )}
          </div>
        </div>

        {error && (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={busy}>取消</Button>
          <Button
            variant="destructive"
            onClick={handleReject}
            disabled={busy}
          >
            驳回
          </Button>
          <Button
            onClick={handleApprove}
            disabled={busy || !draft.trim()}
          >
            {busy ? "保存中…" : edited ? "保存并通过" : "通过"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
