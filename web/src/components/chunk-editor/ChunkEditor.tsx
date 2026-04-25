import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
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
  fetchChunk,
  fetchTaxonomyTree,
  updateChunk,
  deleteChunk,
  splitChunk,
  ConflictError,
} from "@/lib/api"
import {
  Plus,
  Trash2,
  Scissors,
  Save,
  Loader2,
  AlertTriangle,
} from "lucide-react"
import {
  type BridgeLinkRow,
  bridgeLinkRowsFromDetail,
  bridgeLinkRowsToInput,
  getLvl1Options,
  getLvl2Options,
  getLvl3Options,
} from "./types"
import { SplitParagraphView, SplitPreciseView, SplitPreview } from "./SplitMode"

interface ChunkEditorProps {
  chunkId: string
  onMutated: () => void
}

export function ChunkEditor({ chunkId, onMutated }: ChunkEditorProps) {
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
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
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
          <div className="flex items-center gap-3 border-b bg-background px-4 py-2">
            <Scissors className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">
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
                  onClick={() => { setSplitPhase(null); setActionError(null) }}
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
          {splitPhase === "selecting" ? (
            splitSubMode === "paragraph" ? (
              <SplitParagraphView
                content={chunk.content}
                onSelectPosition={(pos) => {
                  setSplitPosition(pos)
                  setSplitPhase("previewing")
                }}
              />
            ) : (
              <SplitPreciseView
                content={chunk.content}
                onSelectPosition={(pos) => {
                  setSplitPosition(pos)
                  setSplitPhase("previewing")
                }}
              />
            )
          ) : splitPosition !== null ? (
            <SplitPreview
              content={chunk.content}
              position={splitPosition}
              splitting={splitting}
              onConfirm={() => handleSplit(splitPosition)}
              onReselect={() => setSplitPhase("selecting")}
              onCancel={() => { setSplitPhase(null); setActionError(null) }}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <Button size="sm" variant="outline" onClick={() => setSplitPhase("selecting")}>
                返回选择拆分位置
              </Button>
            </div>
          )}
        </>
      ) : (
        // --- Normal edit mode ---
        <div className="flex flex-col gap-4 overflow-y-auto p-4">
          {/* Reindex warning */}
          {chunk.needs_reindex && (
            <div className="flex items-center gap-2 rounded-md border border-[var(--yellow-hemp)]/30 bg-[var(--yellow-hemp)]/10 px-3 py-2 text-sm text-[var(--ink-black)]">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              内容已修改，embedding 待更新
            </div>
          )}

          {/* Content textarea */}
          <div className="space-y-1">
            <Label className="text-xs font-medium text-muted-foreground">内容</Label>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="min-h-[200px] resize-y font-mono text-sm"
            />
          </div>

          {/* Section title */}
          <div className="space-y-1">
            <Label className="text-xs font-medium text-muted-foreground">章节标题</Label>
            <Input
              value={sectionTitle}
              onChange={(e) => setSectionTitle(e.target.value)}
              placeholder="章节标题（可选）"
              className="text-sm"
            />
          </div>

          {/* Taxonomy cascading selects */}
          <div className="space-y-2">
            <Label className="text-xs font-medium text-muted-foreground">分类标签</Label>
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
              <Label className="text-xs font-medium text-muted-foreground">桥梁关联</Label>
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
              <p className="text-xs text-muted-foreground">暂无桥梁关联</p>
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
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
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
                setActionError(null)
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
              该 Chunk 已被其他用户修改。您可以强制执行或取消操作。
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
              取消操作
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                setConflictOpen(false)
                conflictRetryFn?.()
              }}
            >
              强制执行
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
