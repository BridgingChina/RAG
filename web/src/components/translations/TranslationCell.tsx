/**
 * TranslationCell — renders one ``*_en`` field with status-driven inline
 * actions. The action group is keyed off ``reviewItem?.status``:
 *
 * - 🔴 pending_ai      → [♻ AI 翻译]
 * - 🟡 ai_generated    → [✓ 通过] [✏ 编辑后通过] [✗ 驳回] [♻ AI 重译]
 * - 🟢 human_reviewed  → [✏ 编辑] [♻ AI 重译]
 * - ⚫ rejected        → [♻ AI 重译]
 *
 * Mutations call the existing /translations/* endpoints. Optimistic UI is
 * intentionally NOT used — callers expect ``onChange`` to fire only when
 * the server confirmed the new state. Failures surface as an inline error
 * banner without mutating parent state, matching the design doc §6.3.
 */
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { TranslationStatusBadge } from "./TranslationStatusBadge"
import { generateTranslation, reviewTranslation } from "@/lib/api"
import type { TranslationReviewItem } from "@/lib/types"
import { cn } from "@/lib/utils"

export type TranslatableTable =
  | "bridges"
  | "knowledge_points"
  | "flashcards"
  | "taxonomy_nodes"
  | "knowledge_point_key_points"

interface Props {
  table: TranslatableTable
  rowId: string
  fieldName: string
  /** zh source value displayed in the paired left column. Forwarded to the
   *  generate endpoint when no review row exists yet. */
  sourceText: string
  /** Existing review record, if any. ``null`` ⇒ render as ``pending_ai``. */
  reviewItem: TranslationReviewItem | null
  /** Called with the new review state after every successful mutation. The
   *  parent owns refetching the business row in the approve / edit cases
   *  (because the *_en column on the business table is now updated). */
  onChange?: (next: TranslationReviewItem) => void
  /** Optional anchor for ``useScrollToTr`` deep-linking. Defaults to fieldName. */
  anchor?: string
  className?: string
}

export function TranslationCell({
  table,
  rowId,
  fieldName,
  sourceText,
  reviewItem,
  onChange,
  anchor,
  className,
}: Props) {
  const status = reviewItem?.status ?? "pending_ai"
  const enText =
    reviewItem?.reviewed_translation ?? reviewItem?.ai_translation ?? ""

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState("")

  // Reset transient state when the review row identity changes (e.g. user
  // navigates to a different KP in the same page shell).
  useEffect(() => {
    setEditing(false)
    setError(null)
    setDraft("")
  }, [reviewItem?.id, fieldName])

  const handleGenerate = async () => {
    setBusy(true); setError(null)
    try {
      const next = await generateTranslation({
        table_name: table,
        row_id: rowId,
        field_name: fieldName,
      })
      onChange?.(next)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const handleReview = async (action: "approve" | "edit" | "reject", text?: string) => {
    if (!reviewItem) return
    setBusy(true); setError(null)
    try {
      const next = await reviewTranslation(reviewItem.id, { action, text })
      onChange?.(next)
      if (action === "edit") setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const startEdit = () => {
    setDraft(enText)
    setEditing(true)
  }

  return (
    <div
      className={cn(
        "rounded-md border bg-muted/20 p-3 transition-shadow",
        className,
      )}
      data-tr={anchor ?? fieldName}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <TranslationStatusBadge status={status} />
        <span className="font-mono text-[10px] text-muted-foreground">
          {fieldName}
        </span>
      </div>

      {editing ? (
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={Math.max(3, Math.min(12, Math.ceil((sourceText.length || 60) / 40)))}
          disabled={busy}
          className="mb-2 text-sm"
          placeholder="编辑后通过将以此版本入库"
        />
      ) : (
        <div className="mb-2 min-h-[2.5rem] text-sm leading-relaxed whitespace-pre-wrap break-words">
          {enText || (
            <em className="text-muted-foreground/60">
              {status === "pending_ai" ? "尚未生成英文译文" : "（空）"}
            </em>
          )}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        {status === "pending_ai" && (
          <Button size="sm" variant="outline" onClick={handleGenerate} disabled={busy}>
            {busy ? "翻译中…" : "♻ AI 翻译"}
          </Button>
        )}

        {status === "ai_generated" && !editing && (
          <>
            <Button size="sm" onClick={() => handleReview("approve")} disabled={busy}>
              ✓ 通过
            </Button>
            <Button size="sm" variant="outline" onClick={startEdit} disabled={busy}>
              ✏ 编辑后通过
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              onClick={() => handleReview("reject")}
              disabled={busy}
            >
              ✗ 驳回
            </Button>
            <Button size="sm" variant="ghost" onClick={handleGenerate} disabled={busy}>
              ♻ AI 重译
            </Button>
          </>
        )}

        {status === "human_reviewed" && !editing && (
          <>
            <Button size="sm" variant="outline" onClick={startEdit} disabled={busy}>
              ✏ 编辑
            </Button>
            <Button size="sm" variant="ghost" onClick={handleGenerate} disabled={busy}>
              ♻ AI 重译
            </Button>
          </>
        )}

        {status === "rejected" && !editing && (
          <Button size="sm" variant="outline" onClick={handleGenerate} disabled={busy}>
            ♻ AI 重译
          </Button>
        )}

        {editing && (
          <>
            <Button
              size="sm"
              onClick={() => handleReview("edit", draft.trim())}
              disabled={busy || !draft.trim()}
            >
              {busy ? "保存中…" : "保存并通过"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => { setEditing(false); setError(null) }}
              disabled={busy}
            >
              取消
            </Button>
          </>
        )}
      </div>

      {error && (
        <div className="mt-2 rounded-sm border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
          {error}
        </div>
      )}
    </div>
  )
}
