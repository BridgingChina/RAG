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

  // Dialog state
  const [splitDialogOpen, setSplitDialogOpen] = useState(false)
  const [splitPos, setSplitPos] = useState("")
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)

  // Action state
  const [saving, setSaving] = useState(false)
  const [splitting, setSplitting] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Textarea ref for cursor position
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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

      await updateChunk(chunk.id, updates)
      refetch()
      onMutated()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }, [chunk, content, sectionTitle, lvl1, lvl2, lvl3, bridgeLinks, refetch, onMutated])

  const handleSplit = useCallback(async () => {
    if (!chunk) return
    setSplitting(true)
    setActionError(null)
    try {
      const pos = Number(splitPos)
      await splitChunk(chunk.id, { position: pos })
      setSplitDialogOpen(false)
      onMutated()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setSplitting(false)
    }
  }, [chunk, splitPos, onMutated])

  const handleDelete = useCallback(async () => {
    if (!chunk) return
    setDeleting(true)
    setActionError(null)
    try {
      await deleteChunk(chunk.id)
      setDeleteDialogOpen(false)
      onMutated()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setDeleting(false)
    }
  }, [chunk, onMutated])

  function openSplitDialog() {
    if (!chunk) return
    const cursorPos = textareaRef.current?.selectionStart
    setSplitPos(
      String(
        cursorPos !== undefined && cursorPos > 0
          ? cursorPos
          : Math.floor(chunk.content.length / 2),
      ),
    )
    setSplitDialogOpen(true)
  }

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
          ref={textareaRef}
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
          onClick={openSplitDialog}
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

      {/* Split dialog */}
      <Dialog open={splitDialogOpen} onOpenChange={setSplitDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>拆分知识块</DialogTitle>
            <DialogDescription>
              在指定字符位置将此知识块分为两部分。当前内容长度：{chunk.content.length} 字符。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>拆分位置（字符索引）</Label>
            <Input
              type="number"
              value={splitPos}
              onChange={(e) => setSplitPos(e.target.value)}
              min={1}
              max={chunk.content.length - 1}
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setSplitDialogOpen(false)}
            >
              取消
            </Button>
            <Button onClick={handleSplit} disabled={splitting}>
              {splitting ? <Loader2 className="h-4 w-4 animate-spin" /> : "确认拆分"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
  } = useApi(() => fetchChunks({ source_id: sid, page_size: 200 }), [sid])

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
              : `共 ${chunks.length} 个块${stale > 0 ? `，${stale} 待索引` : ""}`}
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
