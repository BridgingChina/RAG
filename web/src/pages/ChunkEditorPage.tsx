import { useCallback, useEffect, useRef, useState } from "react"
import { useParams, useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useApi } from "@/hooks/useApi"
import {
  fetchChunks,
  fetchChunk,
  fetchSource,
  fetchTaxonomyTree,
  updateChunk,
  deleteChunk,
  splitChunk,
  mergeChunks,
  batchChunks,
  reindexSource,
  ConflictError,
} from "@/lib/api"
import type {
  ChunkListItem,
  ChunkDetail,
  BridgeLinkInput,
  TaxonomyTreeItem,
} from "@/lib/types"
import {
  ArrowLeft,
  RefreshCw,
  Plus,
  Trash2,
  Scissors,
  Save,
  Loader2,
  AlertTriangle,
} from "lucide-react"

// --- Helpers ---

function staleCount(chunks: ChunkListItem[]): number {
  return chunks.filter((c) => c.needs_reindex).length
}

// --- Split helpers ---

interface ParagraphSegment {
  text: string
  startOffset: number
  endOffset: number
}

function parseContentSegments(content: string): ParagraphSegment[] {
  let parts = content.split("\n\n")
  let separator = "\n\n"

  if (parts.length <= 1) {
    parts = content.split("\n")
    separator = "\n"
  }

  const segments: ParagraphSegment[] = []
  let offset = 0
  for (let i = 0; i < parts.length; i++) {
    const text = parts[i]
    if (text.length > 0) {
      segments.push({
        text,
        startOffset: offset,
        endOffset: offset + text.length,
      })
    }
    offset += text.length
    if (i < parts.length - 1) {
      offset += separator.length
    }
  }
  return segments
}

// --- Split paragraph view (Mode A) ---

interface SplitParagraphViewProps {
  content: string
  onSelectPosition: (position: number) => void
}

function SplitParagraphView({ content, onSelectPosition }: SplitParagraphViewProps) {
  const segments = parseContentSegments(content)
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null)
  const totalLen = content.length

  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-4 py-2 space-y-0">
      {segments.map((seg, i) => (
        <div key={seg.startOffset}>
          {/* Paragraph text */}
          <div
            className={`rounded px-3 py-2 font-mono text-sm whitespace-pre-wrap transition-colors ${
              hoveredIdx !== null && i < hoveredIdx
                ? "bg-blue-50"
                : hoveredIdx !== null && i >= hoveredIdx
                  ? "bg-emerald-50"
                  : ""
            }`}
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
                ✂ {seg.endOffset} 字 | {totalLen - segments[i + 1].startOffset} 字
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

function SplitPreciseView({ content, onSelectPosition }: SplitPreciseViewProps) {
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

interface SplitPreviewProps {
  content: string
  position: number
  splitting: boolean
  onConfirm: () => void
  onReselect: () => void
  onCancel: () => void
}

function SplitPreview({ content, position, splitting, onConfirm, onReselect, onCancel }: SplitPreviewProps) {
  const chunkA = content.slice(0, position)
  const chunkB = content.slice(position)

  return (
    <div className="flex flex-1 min-h-0 flex-col p-4 gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-700">拆分预览</h3>
        <Button size="sm" variant="ghost" onClick={onReselect} className="gap-1 text-xs">
          <ArrowLeft className="h-3 w-3" />
          重选位置
        </Button>
      </div>

      {/* Chunk A */}
      <div className="flex flex-1 min-h-0 flex-col rounded-md border border-blue-200 bg-blue-50">
        <div className="flex items-center justify-between border-b border-blue-200 px-3 py-1.5">
          <span className="text-xs font-medium text-blue-700">Chunk A</span>
          <span className="text-xs text-blue-500">{chunkA.length} 字</span>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono text-sm whitespace-pre-wrap">
          {chunkA}
        </div>
      </div>

      {/* Chunk B */}
      <div className="flex flex-1 min-h-0 flex-col rounded-md border border-emerald-200 bg-emerald-50">
        <div className="flex items-center justify-between border-b border-emerald-200 px-3 py-1.5">
          <span className="text-xs font-medium text-emerald-700">Chunk B</span>
          <span className="text-xs text-emerald-500">{chunkB.length} 字</span>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2 font-mono text-sm whitespace-pre-wrap">
          {chunkB}
        </div>
      </div>

      {/* Action bar */}
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

// --- Taxonomy cascade helpers ---

function getLvl1Options(items: TaxonomyTreeItem[]): TaxonomyTreeItem[] {
  return items
}

function getLvl2Options(
  items: TaxonomyTreeItem[],
  lvl1: string | null,
): TaxonomyTreeItem[] {
  if (!lvl1) return []
  const parent = items.find((i) => i.label === lvl1)
  return parent?.children ?? []
}

function getLvl3Options(
  items: TaxonomyTreeItem[],
  lvl1: string | null,
  lvl2: string | null,
): TaxonomyTreeItem[] {
  if (!lvl1 || !lvl2) return []
  const parent = items.find((i) => i.label === lvl1)
  const sub = parent?.children.find((i) => i.label === lvl2)
  return sub?.children ?? []
}

// --- Bridge links editor ---

interface BridgeLinkRow {
  bridge_id: string
  role: "primary" | "secondary" | "candidate"
  confidence: string
}

function bridgeLinkRowsFromDetail(
  links: ChunkDetail["bridge_links"],
): BridgeLinkRow[] {
  return links.map((l) => ({
    bridge_id: String(l.bridge_id),
    role: l.role as "primary" | "secondary" | "candidate",
    confidence: String(l.confidence),
  }))
}

function bridgeLinkRowsToInput(rows: BridgeLinkRow[]): BridgeLinkInput[] {
  return rows
    .filter((r) => r.bridge_id.trim() !== "")
    .map((r) => ({
      bridge_id: Number(r.bridge_id),
      role: r.role,
      confidence: Number.isNaN(Number(r.confidence))
        ? 1.0
        : Number(r.confidence),
      method: "manual" as const,
    }))
}

// --- Left pane chunk item ---

interface ChunkItemProps {
  chunk: ChunkListItem
  selected: boolean
  checked: boolean
  onSelect: () => void
  onCheck: (checked: boolean) => void
}

function ChunkItem({ chunk, selected, checked, onSelect, onCheck }: ChunkItemProps) {
  return (
    <div
      className={`flex cursor-pointer items-start gap-2 border-b px-3 py-2 hover:bg-slate-50 ${
        selected ? "bg-blue-50 border-l-2 border-l-blue-500" : ""
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
        <div className="flex items-center gap-1 text-xs text-slate-400">
          <span className="font-mono">#{chunk.id}</span>
          {chunk.needs_reindex && (
            <Badge className="bg-orange-100 text-orange-700 text-[10px] px-1 py-0">
              待索引
            </Badge>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-xs text-slate-700">
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

// --- Right pane: single chunk editor ---

interface ChunkEditorProps {
  chunkId: number
  onMutated: () => void
}

function ChunkEditor({ chunkId, onMutated }: ChunkEditorProps) {
  const { data: chunk, loading, error, refetch } = useApi(
    () => fetchChunk(chunkId),
    [chunkId],
  )

  const { data: taxTree } = useApi(fetchTaxonomyTree, [])

  // Form state
  const [content, setContent] = useState("")
  const [sectionTitle, setSectionTitle] = useState("")
  const [lvl1, setLvl1] = useState<string | null>(null)
  const [lvl2, setLvl2] = useState<string | null>(null)
  const [lvl3, setLvl3] = useState<string | null>(null)
  const [bridgeLinks, setBridgeLinks] = useState<BridgeLinkRow[]>([])

  // Split mode state
  const [splitPhase, setSplitPhase] = useState<null | "selecting" | "previewing">(null)
  const [splitSubMode, setSplitSubMode] = useState<"paragraph" | "precise">("paragraph")
  const [splitPosition, setSplitPosition] = useState<number | null>(null)

  // Dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)

  // Conflict dialog state
  const [conflictOpen, setConflictOpen] = useState(false)
  const [conflictRetryFn, setConflictRetryFn] = useState<(() => void) | null>(null)

  // Action state
  const [saving, setSaving] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Sync form with loaded chunk
  useEffect(() => {
    if (chunk) {
      setContent(chunk.content)
      setSectionTitle(chunk.section_title ?? "")
      setLvl1(chunk.lvl1)
      setLvl2(chunk.lvl2)
      setLvl3(chunk.lvl3)
      setBridgeLinks(bridgeLinkRowsFromDetail(chunk.bridge_links))
      setActionError(null)
    }
  }, [chunk])

  // Taxonomy options
  const taxItems = taxTree?.items ?? []
  const lvl1Options = getLvl1Options(taxItems)
  const lvl2Options = getLvl2Options(taxItems, lvl1)
  const lvl3Options = getLvl3Options(taxItems, lvl1, lvl2)

  function handleConflictError(err: unknown, retryWithoutLock: () => void): boolean {
    if (err instanceof ConflictError) {
      setConflictRetryFn(() => retryWithoutLock)
      setConflictOpen(true)
      return true
    }
    return false
  }

  const handleSave = useCallback(async () => {
    if (!chunk) return
    setSaving(true)
    setActionError(null)
    try {
      // Only send changed fields
      const updates: Parameters<typeof updateChunk>[1] = {}
      if (content !== chunk.content) updates.content = content
      if ((sectionTitle || null) !== chunk.section_title)
        updates.section_title = sectionTitle || null
      if (lvl1 !== chunk.lvl1) updates.lvl1 = lvl1
      if (lvl2 !== chunk.lvl2) updates.lvl2 = lvl2
      if (lvl3 !== chunk.lvl3) updates.lvl3 = lvl3
      // Always send bridge_links if they changed
      const newLinks = bridgeLinkRowsToInput(bridgeLinks)
      const origLinks = bridgeLinkRowsToInput(
        bridgeLinkRowsFromDetail(chunk.bridge_links),
      )
      if (JSON.stringify(newLinks) !== JSON.stringify(origLinks)) {
        updates.bridge_links = newLinks
      }

      // Include optimistic lock timestamp
      updates.expected_updated_at = chunk.updated_at

      await updateChunk(chunk.id, updates)
      refetch()
      onMutated()
    } catch (e) {
      if (handleConflictError(e, () => {
        // Retry without the lock — force overwrite
        const updates: Parameters<typeof updateChunk>[1] = {}
        if (content !== chunk.content) updates.content = content
        if ((sectionTitle || null) !== chunk.section_title)
          updates.section_title = sectionTitle || null
        if (lvl1 !== chunk.lvl1) updates.lvl1 = lvl1
        if (lvl2 !== chunk.lvl2) updates.lvl2 = lvl2
        if (lvl3 !== chunk.lvl3) updates.lvl3 = lvl3
        const newLinks = bridgeLinkRowsToInput(bridgeLinks)
        const origLinks = bridgeLinkRowsToInput(
          bridgeLinkRowsFromDetail(chunk.bridge_links),
        )
        if (JSON.stringify(newLinks) !== JSON.stringify(origLinks)) {
          updates.bridge_links = newLinks
        }
        setSaving(true)
        updateChunk(chunk.id, updates)
          .then(() => { refetch(); onMutated() })
          .catch((err2) => setActionError(err2 instanceof Error ? err2.message : String(err2)))
          .finally(() => setSaving(false))
      })) return
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }, [chunk, content, sectionTitle, lvl1, lvl2, lvl3, bridgeLinks, refetch, onMutated])

  const handleSplit = useCallback(async (position: number) => {
    if (!chunk) return
    setSplitting(true)
    setActionError(null)
    try {
      await splitChunk(chunk.id, { position, expected_updated_at: chunk.updated_at })
      setSplitPhase(null)
      onMutated()
    } catch (e) {
      if (handleConflictError(e, () => {
        setSplitting(true)
        splitChunk(chunk.id, { position })
          .then(() => { setSplitPhase(null); onMutated() })
          .catch((err2) => setActionError(err2 instanceof Error ? err2.message : String(err2)))
          .finally(() => setSplitting(false))
      })) return
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSplitting(false)
    }
  }, [chunk, onMutated])

  const handleDelete = useCallback(async () => {
    if (!chunk) return
    setDeleting(true)
    setActionError(null)
    try {
      await deleteChunk(chunk.id, chunk.updated_at)
      setDeleteDialogOpen(false)
      onMutated()
    } catch (e) {
      if (handleConflictError(e, () => {
        // Retry without lock — force delete
        setDeleting(true)
        setDeleteDialogOpen(false)
        deleteChunk(chunk.id)
          .then(() => onMutated())
          .catch((err2) => setActionError(err2 instanceof Error ? err2.message : String(err2)))
          .finally(() => setDeleting(false))
      })) return
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setDeleting(false)
    }
  }, [chunk, onMutated])

  const paragraphModeAvailable = chunk ? /\n/.test(chunk.content) : false

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
      </div>
    )
  }

  if (error || !chunk) {
    return (
      <div className="p-6 text-sm text-destructive">
        {error ?? "加载失败"}
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {splitPhase !== null ? (
        // --- Split mode ---
        <>
          {/* Split mode header */}
          <div className="flex items-center gap-3 border-b bg-white px-4 py-2">
            <Scissors className="h-4 w-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-700">
              {splitPhase === "selecting" ? "选择拆分位置" : "拆分预览"}
            </span>

            {splitPhase === "selecting" && (
              <div className="ml-auto flex items-center gap-1">
                <Button
                  size="sm"
                  variant={splitSubMode === "paragraph" ? "default" : "outline"}
                  disabled={!paragraphModeAvailable}
                  onClick={() => setSplitSubMode("paragraph")}
                  className="h-7 px-2 text-xs"
                >
                  段落模式
                </Button>
                <Button
                  size="sm"
                  variant={splitSubMode === "precise" ? "default" : "outline"}
                  onClick={() => setSplitSubMode("precise")}
                  className="h-7 px-2 text-xs"
                >
                  精确模式
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSplitPhase(null)}
                  className="ml-2 h-7 px-2 text-xs"
                >
                  取消
                </Button>
              </div>
            )}
          </div>

          {/* Error display */}
          {actionError && (
            <p className="px-4 pt-2 text-xs text-destructive">{actionError}</p>
          )}

          {/* Split content area */}
          {splitPhase === "selecting" && splitSubMode === "paragraph" && (
            <SplitParagraphView
              content={chunk.content}
              onSelectPosition={(pos) => {
                setSplitPosition(pos)
                setSplitPhase("previewing")
              }}
            />
          )}
          {splitPhase === "selecting" && splitSubMode === "precise" && (
            <SplitPreciseView
              content={chunk.content}
              onSelectPosition={(pos) => {
                setSplitPosition(pos)
                setSplitPhase("previewing")
              }}
            />
          )}
          {splitPhase === "previewing" && splitPosition !== null && (
            <SplitPreview
              content={chunk.content}
              position={splitPosition}
              splitting={splitting}
              onConfirm={() => handleSplit(splitPosition)}
              onReselect={() => setSplitPhase("selecting")}
              onCancel={() => setSplitPhase(null)}
            />
          )}
        </>
      ) : (
        // --- Normal edit mode ---
        <div className="flex flex-col gap-4 overflow-y-auto p-4">
          {/* Reindex warning */}
          {chunk.needs_reindex && (
            <div className="flex items-center gap-2 rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-sm text-orange-700">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              内容已修改，embedding 待更新
            </div>
          )}

          {/* Content textarea */}
          <div className="space-y-1">
            <Label className="text-xs font-medium text-slate-600">内容</Label>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="min-h-[200px] resize-y font-mono text-sm"
            />
          </div>

          {/* Section title */}
          <div className="space-y-1">
            <Label className="text-xs font-medium text-slate-600">章节标题</Label>
            <Input
              value={sectionTitle}
              onChange={(e) => setSectionTitle(e.target.value)}
              placeholder="章节标题（可选）"
              className="text-sm"
            />
          </div>

          {/* Taxonomy cascading selects */}
          <div className="space-y-2">
            <Label className="text-xs font-medium text-slate-600">分类标签</Label>
            <div className="grid grid-cols-3 gap-2">
              {/* lvl1 */}
              <Select
                value={lvl1 ?? "__none__"}
                onValueChange={(v) => {
                  const next = v === "__none__" ? null : v
                  setLvl1(next)
                  setLvl2(null)
                  setLvl3(null)
                }}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="lvl1" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— 无 —</SelectItem>
                  {lvl1Options.map((o) => (
                    <SelectItem key={o.node_id} value={o.label}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* lvl2 */}
              <Select
                value={lvl2 ?? "__none__"}
                onValueChange={(v) => {
                  const next = v === "__none__" ? null : v
                  setLvl2(next)
                  setLvl3(null)
                }}
                disabled={!lvl1}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="lvl2" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— 无 —</SelectItem>
                  {lvl2Options.map((o) => (
                    <SelectItem key={o.node_id} value={o.label}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {/* lvl3 */}
              <Select
                value={lvl3 ?? "__none__"}
                onValueChange={(v) => {
                  setLvl3(v === "__none__" ? null : v)
                }}
                disabled={!lvl2}
              >
                <SelectTrigger className="text-xs">
                  <SelectValue placeholder="lvl3" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">— 无 —</SelectItem>
                  {lvl3Options.map((o) => (
                    <SelectItem key={o.node_id} value={o.label}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Bridge links */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium text-slate-600">桥梁关联</Label>
              <Button
                size="sm"
                variant="outline"
                className="h-6 px-2 text-xs"
                onClick={() =>
                  setBridgeLinks([
                    ...bridgeLinks,
                    { bridge_id: "", role: "secondary", confidence: "1.0" },
                  ])
                }
              >
                <Plus className="h-3 w-3 mr-1" />
                添加
              </Button>
            </div>
            {bridgeLinks.length === 0 ? (
              <p className="text-xs text-slate-400">暂无桥梁关联</p>
            ) : (
              <div className="space-y-1">
                {bridgeLinks.map((row, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <Input
                      value={row.bridge_id}
                      onChange={(e) => {
                        const next = [...bridgeLinks]
                        next[i] = { ...next[i], bridge_id: e.target.value }
                        setBridgeLinks(next)
                      }}
                      placeholder="Bridge ID"
                      className="h-7 w-20 text-xs font-mono"
                    />
                    <Select
                      value={row.role}
                      onValueChange={(v) => {
                        const next = [...bridgeLinks]
                        next[i] = {
                          ...next[i],
                          role: v as "primary" | "secondary" | "candidate",
                        }
                        setBridgeLinks(next)
                      }}
                    >
                      <SelectTrigger className="h-7 w-24 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="primary">主桥</SelectItem>
                        <SelectItem value="secondary">次桥</SelectItem>
                        <SelectItem value="candidate">候选</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      value={row.confidence}
                      onChange={(e) => {
                        const next = [...bridgeLinks]
                        next[i] = { ...next[i], confidence: e.target.value }
                        setBridgeLinks(next)
                      }}
                      placeholder="置信度"
                      className="h-7 w-16 text-xs"
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 w-7 p-0 text-slate-400 hover:text-destructive"
                      onClick={() =>
                        setBridgeLinks(bridgeLinks.filter((_, idx) => idx !== i))
                      }
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Action error */}
          {actionError && (
            <p className="text-xs text-destructive">{actionError}</p>
          )}

          {/* Action buttons */}
          <div className="flex gap-2 border-t pt-3">
            <Button
              size="sm"
              onClick={handleSave}
              disabled={saving}
              className="gap-1"
            >
              {saving ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Save className="h-3 w-3" />
              )}
              保存
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setSplitPhase("selecting")
                setSplitSubMode(paragraphModeAvailable ? "paragraph" : "precise")
                setSplitPosition(null)
              }}
              className="gap-1"
            >
              <Scissors className="h-3 w-3" />
              拆分
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setDeleteDialogOpen(true)}
              className="gap-1 ml-auto"
            >
              <Trash2 className="h-3 w-3" />
              删除
            </Button>
          </div>
        </div>
      )}

      {/* Delete dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除知识块 #{chunk.id} 吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Conflict dialog */}
      <Dialog open={conflictOpen} onOpenChange={setConflictOpen}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>编辑冲突</DialogTitle>
            <DialogDescription>
              该 Chunk 已被其他用户修改。您可以强制覆盖或放弃本次更改。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setConflictOpen(false)
                refetch()
              }}
            >
              放弃修改
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConflictOpen(false)
                conflictRetryFn?.()
              }}
            >
              强制覆盖
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// --- Batch toolbar ---

interface BatchToolbarProps {
  selectedIds: number[]
  taxItems: TaxonomyTreeItem[]
  onMutated: () => void
  onClearSelection: () => void
}

function BatchToolbar({
  selectedIds,
  taxItems,
  onMutated,
  onClearSelection,
}: BatchToolbarProps) {
  const [tagDialogOpen, setTagDialogOpen] = useState(false)
  const [bridgeDialogOpen, setBridgeDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [merging, setMerging] = useState(false)
  const [acting, setActing] = useState(false)
  const [batchError, setBatchError] = useState<string | null>(null)

  // Tag batch state
  const [bLvl1, setBLvl1] = useState<string | null>(null)
  const [bLvl2, setBLvl2] = useState<string | null>(null)
  const [bLvl3, setBLvl3] = useState<string | null>(null)

  // Bridge batch state
  const [bBridgeId, setBBridgeId] = useState("")

  const lvl1Options = getLvl1Options(taxItems)
  const lvl2Options = getLvl2Options(taxItems, bLvl1)
  const lvl3Options = getLvl3Options(taxItems, bLvl1, bLvl2)

  const handleBatchTag = useCallback(async () => {
    setActing(true)
    setBatchError(null)
    try {
      await batchChunks({
        chunk_ids: selectedIds,
        action: "update",
        updates: { lvl1: bLvl1, lvl2: bLvl2, lvl3: bLvl3 },
      })
      setTagDialogOpen(false)
      onClearSelection()
      onMutated()
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : String(e))
    } finally {
      setActing(false)
    }
  }, [selectedIds, bLvl1, bLvl2, bLvl3, onClearSelection, onMutated])

  const handleBatchBridge = useCallback(async () => {
    setActing(true)
    setBatchError(null)
    try {
      const bid = bBridgeId.trim() ? Number(bBridgeId) : null
      await batchChunks({
        chunk_ids: selectedIds,
        action: "update",
        updates: { bridge_id: bid },
      })
      setBridgeDialogOpen(false)
      onClearSelection()
      onMutated()
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : String(e))
    } finally {
      setActing(false)
    }
  }, [selectedIds, bBridgeId, onClearSelection, onMutated])

  const handleMerge = useCallback(async () => {
    setMerging(true)
    setBatchError(null)
    try {
      const sorted = [...selectedIds].sort((a, b) => a - b)
      await mergeChunks({ chunk_ids: sorted })
      onClearSelection()
      onMutated()
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : String(e))
    } finally {
      setMerging(false)
    }
  }, [selectedIds, onClearSelection, onMutated])

  const handleBatchDelete = useCallback(async () => {
    setActing(true)
    setBatchError(null)
    try {
      await batchChunks({
        chunk_ids: selectedIds,
        action: "delete",
      })
      setDeleteDialogOpen(false)
      onClearSelection()
      onMutated()
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : String(e))
    } finally {
      setActing(false)
    }
  }, [selectedIds, onClearSelection, onMutated])

  return (
    <>
      <div className="fixed bottom-0 left-0 right-0 z-10 flex items-center gap-3 border-t bg-white px-6 py-3 shadow-md">
        <span className="text-sm font-medium text-slate-700">
          已选 {selectedIds.length} 项
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setBLvl1(null)
            setBLvl2(null)
            setBLvl3(null)
            setBatchError(null)
            setTagDialogOpen(true)
          }}
        >
          改 Tag
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setBBridgeId("")
            setBatchError(null)
            setBridgeDialogOpen(true)
          }}
        >
          改 Bridge
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={handleMerge}
          disabled={merging || selectedIds.length < 2}
        >
          {merging ? <Loader2 className="h-3 w-3 animate-spin" /> : "合并"}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => {
            setBatchError(null)
            setDeleteDialogOpen(true)
          }}
        >
          删除
        </Button>
        {batchError && (
          <span className="text-xs text-destructive">{batchError}</span>
        )}
      </div>

      {/* Batch tag dialog */}
      <Dialog open={tagDialogOpen} onOpenChange={setTagDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>批量改 Tag</DialogTitle>
            <DialogDescription>
              将选中 {selectedIds.length} 个知识块的分类标签更新为：
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-3 gap-2">
            <Select
              value={bLvl1 ?? "__none__"}
              onValueChange={(v) => {
                setBLvl1(v === "__none__" ? null : v)
                setBLvl2(null)
                setBLvl3(null)
              }}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="lvl1" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— 无 —</SelectItem>
                {lvl1Options.map((o) => (
                  <SelectItem key={o.node_id} value={o.label}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={bLvl2 ?? "__none__"}
              onValueChange={(v) => {
                setBLvl2(v === "__none__" ? null : v)
                setBLvl3(null)
              }}
              disabled={!bLvl1}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="lvl2" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— 无 —</SelectItem>
                {lvl2Options.map((o) => (
                  <SelectItem key={o.node_id} value={o.label}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={bLvl3 ?? "__none__"}
              onValueChange={(v) => setBLvl3(v === "__none__" ? null : v)}
              disabled={!bLvl2}
            >
              <SelectTrigger className="text-xs">
                <SelectValue placeholder="lvl3" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— 无 —</SelectItem>
                {lvl3Options.map((o) => (
                  <SelectItem key={o.node_id} value={o.label}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {batchError && (
            <p className="text-xs text-destructive">{batchError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTagDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleBatchTag} disabled={acting}>
              {acting ? <Loader2 className="h-4 w-4 animate-spin" /> : "确认"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Batch bridge dialog */}
      <Dialog open={bridgeDialogOpen} onOpenChange={setBridgeDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>批量改 Bridge</DialogTitle>
            <DialogDescription>
              将选中 {selectedIds.length} 个知识块的桥梁 ID 更新为：
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Bridge ID（留空表示清除）</Label>
            <Input
              value={bBridgeId}
              onChange={(e) => setBBridgeId(e.target.value)}
              placeholder="桥梁 ID"
              className="font-mono"
            />
          </div>
          {batchError && (
            <p className="text-xs text-destructive">{batchError}</p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setBridgeDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleBatchBridge} disabled={acting}>
              {acting ? <Loader2 className="h-4 w-4 animate-spin" /> : "确认"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Batch delete dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认批量删除</DialogTitle>
            <DialogDescription>
              确定要删除选中的 {selectedIds.length} 个知识块吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          {batchError && (
            <p className="text-xs text-destructive">{batchError}</p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleBatchDelete}
              disabled={acting}
            >
              {acting ? <Loader2 className="h-4 w-4 animate-spin" /> : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

// --- Main page ---

export function Component() {
  const { sourceId } = useParams()
  const navigate = useNavigate()
  const sid = Number(sourceId)

  // Source info
  const { data: source } = useApi(() => fetchSource(sid), [sid])

  // Chunk list
  const {
    data: chunksData,
    loading: chunksLoading,
    refetch: refetchChunks,
  } = useApi(() => fetchChunks({ source_id: sid, page_size: 100 }), [sid])

  // Taxonomy tree (for batch toolbar)
  const { data: taxTree } = useApi(fetchTaxonomyTree, [])

  // Selection state
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<number>>(new Set())

  // Reindex state
  const [reindexing, setReindexing] = useState(false)
  const [reindexError, setReindexError] = useState<string | null>(null)

  // Sort ascending by id (API returns descending)
  const chunks: ChunkListItem[] = [...(chunksData?.items ?? [])].sort(
    (a, b) => a.id - b.id,
  )

  const stale = staleCount(chunks)

  // When chunks refresh, auto-select first if nothing selected
  useEffect(() => {
    if (chunks.length > 0 && selectedId === null) {
      setSelectedId(chunks[0].id)
    }
  }, [chunks.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Clear selection for deleted/merged items
  const handleMutated = useCallback(() => {
    setCheckedIds(new Set())
    refetchChunks()
    // selectedId might now be invalid; clear it so the list re-auto-selects
    setSelectedId(null)
  }, [refetchChunks])

  // After refetch, re-select an appropriate chunk
  useEffect(() => {
    if (selectedId === null && chunks.length > 0) {
      setSelectedId(chunks[0].id)
    }
  }, [chunks, selectedId])

  function toggleCheck(id: number, checked: boolean) {
    setCheckedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  async function handleReindex() {
    setReindexing(true)
    setReindexError(null)
    try {
      await reindexSource(sid)
      refetchChunks()
    } catch (e) {
      setReindexError(e instanceof Error ? e.message : String(e))
    } finally {
      setReindexing(false)
    }
  }

  const checkedArray = Array.from(checkedIds)
  const showBatchToolbar = checkedArray.length >= 2

  return (
    <>
      <PageHeader
        title={`校对 Chunks — ${source?.title ?? `来源 #${sid}`}`}
        description={reindexError ?? undefined}
      >
        <Button
          size="sm"
          variant="outline"
          onClick={handleReindex}
          disabled={reindexing}
          className="gap-1"
        >
          {reindexing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          重新索引
          {stale > 0 && (
            <Badge className="ml-1 bg-orange-500 text-white text-xs px-1.5 py-0">
              {stale}
            </Badge>
          )}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate(`/sources/${sid}`)}
          className="gap-1"
        >
          <ArrowLeft className="h-4 w-4" />
          返回来源
        </Button>
      </PageHeader>

      {/* Dual pane layout */}
      <div
        className="flex overflow-hidden"
        style={{ height: "calc(100vh - 3.5rem)" }}
      >
        {/* Left pane */}
        <aside className="flex w-80 shrink-0 flex-col border-r bg-white">
          <div className="border-b px-3 py-2 text-xs text-slate-400">
            {chunksLoading
              ? "加载中…"
              : `共 ${chunksData?.total ?? chunks.length} 个块${stale > 0 ? `，${stale} 待索引` : ""}`}
            {!chunksLoading && chunksData && chunksData.total > chunks.length && (
              <span className="ml-1 text-orange-500">
                （仅显示前 {chunks.length} 个）
              </span>
            )}
          </div>
          <div className="flex-1 overflow-y-auto">
            {chunks.map((chunk) => (
              <ChunkItem
                key={chunk.id}
                chunk={chunk}
                selected={selectedId === chunk.id}
                checked={checkedIds.has(chunk.id)}
                onSelect={() => setSelectedId(chunk.id)}
                onCheck={(v) => toggleCheck(chunk.id, v)}
              />
            ))}
            {!chunksLoading && chunks.length === 0 && (
              <p className="p-4 text-xs text-slate-400">暂无知识块</p>
            )}
          </div>
        </aside>

        {/* Right pane */}
        <main className="flex-1 overflow-hidden bg-slate-50">
          {selectedId !== null ? (
            <ChunkEditor
              key={selectedId}
              chunkId={selectedId}
              onMutated={handleMutated}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              从左侧选择一个知识块开始编辑
            </div>
          )}
        </main>
      </div>

      {/* Batch toolbar */}
      {showBatchToolbar && (
        <BatchToolbar
          selectedIds={checkedArray}
          taxItems={taxTree?.items ?? []}
          onMutated={handleMutated}
          onClearSelection={() => setCheckedIds(new Set())}
        />
      )}
    </>
  )
}
