import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { ArrowLeft, Scissors, Loader2 } from "lucide-react"
import { parseContentSegments, segmentBgClass } from "./types"

// --- Split paragraph view (Mode A) ---

interface SplitParagraphViewProps {
  content: string
  onSelectPosition: (position: number) => void
}

export function SplitParagraphView({ content, onSelectPosition }: SplitParagraphViewProps) {
  const segments = parseContentSegments(content)
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)
  const totalLen = content.length

  if (segments.length === 0) {
    return <p className="px-4 py-8 text-sm text-slate-400">内容为空，无法拆分</p>
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-4 py-2">
      {segments.map((seg, i) => (
        <div key={seg.startOffset}>
          {/* Paragraph text */}
          <div
            className={`rounded px-3 py-2 font-mono text-sm whitespace-pre-wrap transition-colors ${segmentBgClass(i, hoveredIdx)}`}
          >
            {seg.text}
          </div>

          {/* Divider between paragraphs (not after last) */}
          {i < segments.length - 1 && (
            <div
              className="group flex cursor-pointer items-center gap-2 py-1 px-3 my-1 select-none"
              onMouseEnter={() => setHoveredIdx(i + 1)}
              onMouseLeave={() => setHoveredIdx(null)}
              onClick={() => onSelectPosition(segments[i + 1].startOffset)}
            >
              <div className="flex-1 border-t border-dashed border-slate-300 group-hover:border-blue-400 transition-colors" />
              <span className="shrink-0 text-xs text-slate-400 group-hover:text-blue-600 transition-colors">
                ✂ {segments[i + 1].startOffset} 字 | {totalLen - segments[i + 1].startOffset} 字
              </span>
              <div className="flex-1 border-t border-dashed border-slate-300 group-hover:border-blue-400 transition-colors" />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// --- Split precise view (Mode C) ---

interface SplitPreciseViewProps {
  content: string
  onSelectPosition: (position: number) => void
}

export function SplitPreciseView({ content, onSelectPosition }: SplitPreciseViewProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [cursorPos, setCursorPos] = useState<number>(0)

  function handleSelect() {
    const pos = textareaRef.current?.selectionStart ?? 0
    setCursorPos(pos)
  }

  const canSplit = cursorPos > 0 && cursorPos < content.length

  return (
    <div className="flex flex-1 min-h-0 flex-col px-4 py-2 gap-2">
      <Textarea
        ref={textareaRef}
        value={content}
        readOnly
        onSelect={handleSelect}
        onClick={handleSelect}
        className="flex-1 min-h-0 resize-none font-mono text-sm"
      />
      <div className="flex items-center justify-between rounded-md border bg-white px-3 py-2">
        <span className="text-xs text-slate-500">
          {canSplit
            ? `光标: 第 ${cursorPos} 字符 · 上半 ${cursorPos} 字 | 下半 ${content.length - cursorPos} 字`
            : "点击文本中的位置来设定拆分点"}
        </span>
        <Button
          size="sm"
          disabled={!canSplit}
          onClick={() => onSelectPosition(cursorPos)}
          className="gap-1"
        >
          <Scissors className="h-3 w-3" />
          在此拆分
        </Button>
      </div>
    </div>
  )
}

// --- Split preview ---

const CHUNK_CARD_STYLES = {
  blue: { border: "border-blue-200", bg: "bg-blue-50", label: "text-blue-700", count: "text-blue-500" },
  emerald: { border: "border-emerald-200", bg: "bg-emerald-50", label: "text-emerald-700", count: "text-emerald-500" },
} as const

function ChunkPreviewCard({ label, content, color }: { label: string; content: string; color: "blue" | "emerald" }) {
  const s = CHUNK_CARD_STYLES[color]
  return (
    <div className={`flex flex-1 min-h-0 flex-col rounded-md border ${s.border} ${s.bg}`}>
      <div className={`flex items-center justify-between border-b ${s.border} px-3 py-1.5`}>
        <span className={`text-xs font-medium ${s.label}`}>{label}</span>
        <span className={`text-xs ${s.count}`}>{content.length} 字</span>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono text-sm whitespace-pre-wrap">
        {content}
      </div>
    </div>
  )
}

interface SplitPreviewProps {
  content: string
  position: number
  splitting: boolean
  onConfirm: () => void
  onReselect: () => void
  onCancel: () => void
}

export function SplitPreview({ content, position, splitting, onConfirm, onReselect, onCancel }: SplitPreviewProps) {
  const chunkA = content.slice(0, position)
  const chunkB = content.slice(position)

  return (
    <div className="flex flex-1 min-h-0 flex-col p-4 gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">拆分预览</h3>
        <Button size="sm" variant="ghost" onClick={onReselect} className="gap-1 text-xs">
          <ArrowLeft className="h-3 w-3" />
          重选位置
        </Button>
      </div>

      <ChunkPreviewCard label="Chunk A" content={chunkA} color="blue" />
      <ChunkPreviewCard label="Chunk B" content={chunkB} color="emerald" />

      <div className="flex items-center justify-end gap-2 border-t pt-3">
        <Button size="sm" variant="outline" onClick={onCancel}>
          取消
        </Button>
        <Button size="sm" onClick={onConfirm} disabled={splitting} className="gap-1">
          {splitting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Scissors className="h-3 w-3" />}
          确认拆分
        </Button>
      </div>
    </div>
  )
}
