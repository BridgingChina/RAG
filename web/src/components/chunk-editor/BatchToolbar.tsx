import { useCallback, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
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
import { batchChunks, mergeChunks } from "@/lib/api"
import type { TaxonomyTreeItem } from "@/lib/types"
import { Loader2 } from "lucide-react"
import { getLvl1Options, getLvl2Options, getLvl3Options } from "./types"

interface BatchToolbarProps {
  selectedIds: string[]
  taxItems: TaxonomyTreeItem[]
  onMutated: () => void
  onClearSelection: () => void
}

export function BatchToolbar({
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
      const bid = bBridgeId.trim() || null
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
      const sorted = [...selectedIds].sort((a, b) => a.localeCompare(b))
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
