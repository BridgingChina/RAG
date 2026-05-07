/**
 * TranslationStatusBadge — small colored-dot + label combo for the four
 * translation_reviews.status values. Mirrors the badge legend in the design
 * doc (§3.3): 🔴 pending_ai · 🟡 ai_generated · 🟢 human_reviewed · ⚫ rejected.
 */
import type { TranslationStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

interface PaletteEntry {
  dot: string
  label: string
}

const PALETTE: Record<TranslationStatus, PaletteEntry> = {
  pending_ai:     { dot: "bg-red-500",    label: "待翻译" },
  ai_generated:   { dot: "bg-yellow-500", label: "待审校" },
  human_reviewed: { dot: "bg-green-500",  label: "已审校" },
  rejected:       { dot: "bg-gray-700",   label: "已驳回" },
}

interface Props {
  status: TranslationStatus
  className?: string
}

export function TranslationStatusBadge({ status, className }: Props) {
  const { dot, label } = PALETTE[status]
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-xs text-muted-foreground",
        className,
      )}
      data-tr-status={status}
    >
      <span
        data-testid="tr-status-dot"
        className={cn("h-2 w-2 shrink-0 rounded-full", dot)}
      />
      <span>{label}</span>
    </span>
  )
}
