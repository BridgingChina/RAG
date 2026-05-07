/**
 * KeyPointTranslationRow — paired zh/en display for one
 * ``knowledge_point_key_points`` record. Two stacked field rows
 * (summary, explanation), each rendering ``zh`` left and a
 * ``<TranslationCell>`` right.
 *
 * The parent (KP detail page) owns:
 * - fetching reviews via ``fetchTranslationsByRow({ table: "knowledge_point_key_points",
 *   row_id: <comma-joined key_point ids> })``
 * - building the per-keypoint ``reviews`` map keyed by ``field_name``
 * - refetching when ``onChange`` fires (the business row's *_en column
 *   has been written by the backend during approve / edit).
 */
import { TranslationCell } from "./TranslationCell"
import type { TranslationReviewItem } from "@/lib/types"

export interface KeyPointInput {
  id: string
  summary: string
  explanation: string | null
}

interface Props {
  keyPoint: KeyPointInput
  /** Indexed by field_name: { summary_en, explanation_en } */
  reviews: Record<string, TranslationReviewItem | null>
  onChange?: (next: TranslationReviewItem) => void
  /** Used to scope the deep-link anchor in nested key_point cells.
   *  e.g. ``key_points.<keyPoint.id>.summary_en`` */
  anchorPrefix?: string
}

export function KeyPointTranslationRow({
  keyPoint,
  reviews,
  onChange,
  anchorPrefix,
}: Props) {
  const anchorFor = (field: string) =>
    anchorPrefix ? `${anchorPrefix}.${field}` : field

  return (
    <div className="space-y-3 rounded-md border border-dashed bg-background/40 p-3">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            要点 (zh)
          </label>
          <div className="rounded-md border bg-muted/30 p-3 text-sm leading-relaxed whitespace-pre-wrap">
            {keyPoint.summary || <em className="text-muted-foreground/60">（空）</em>}
          </div>
        </div>
        <TranslationCell
          table="knowledge_point_key_points"
          rowId={keyPoint.id}
          fieldName="summary_en"
          sourceText={keyPoint.summary}
          reviewItem={reviews.summary_en ?? null}
          onChange={onChange}
          anchor={anchorFor("summary_en")}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            说明 (zh)
          </label>
          <div className="rounded-md border bg-muted/30 p-3 text-sm leading-relaxed whitespace-pre-wrap">
            {keyPoint.explanation || <em className="text-muted-foreground/60">（空）</em>}
          </div>
        </div>
        <TranslationCell
          table="knowledge_point_key_points"
          rowId={keyPoint.id}
          fieldName="explanation_en"
          sourceText={keyPoint.explanation ?? ""}
          reviewItem={reviews.explanation_en ?? null}
          onChange={onChange}
          anchor={anchorFor("explanation_en")}
        />
      </div>
    </div>
  )
}
