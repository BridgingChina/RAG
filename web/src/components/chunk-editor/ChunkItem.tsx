import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import type { ChunkListItem } from "@/lib/types"

interface ChunkItemProps {
  chunk: ChunkListItem
  selected: boolean
  checked: boolean
  onSelect: () => void
  onCheck: (checked: boolean) => void
}

export function ChunkItem({ chunk, selected, checked, onSelect, onCheck }: ChunkItemProps) {
  return (
    <div
      className={`flex cursor-pointer items-start gap-2 border-b px-3 py-2 hover:bg-secondary/40 ${
        selected ? "bg-secondary text-[var(--songci-celadon-deep)]" : ""
      }`}
      onClick={onSelect}
    >
      <div
        className="mt-0.5 shrink-0"
        onClick={(e) => {
          e.stopPropagation()
        }}
      >
        <Checkbox
          checked={checked}
          onCheckedChange={(val) => onCheck(!!val)}
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <span className="font-mono">#{chunk.id}</span>
          {chunk.needs_reindex && (
            <Badge className="bg-[var(--yellow-hemp)]/20 text-[var(--ink-black)] text-[10px] px-1 py-0">
              待索引
            </Badge>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs text-foreground/80">
          {chunk.content_preview}
        </p>
        <div className="mt-1 flex flex-wrap gap-1">
          {chunk.lvl1 && (
            <Badge variant="secondary" className="text-[10px] px-1 py-0">
              {chunk.lvl1}
            </Badge>
          )}
          {chunk.bridge_name && (
            <Badge variant="outline" className="text-[10px] px-1 py-0">
              {chunk.bridge_name}
            </Badge>
          )}
        </div>
      </div>
    </div>
  )
}
