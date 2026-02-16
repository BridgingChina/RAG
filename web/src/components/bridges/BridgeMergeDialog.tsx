import { useCallback, useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { fetchBridges, mergeBridge } from "@/lib/api"
import type { BridgeDetail, BridgeListItem } from "@/lib/types"

interface BridgeMergeDialogProps {
  targetBridge: BridgeDetail
  open: boolean
  onOpenChange: (open: boolean) => void
  onMerged: () => void
}

export function BridgeMergeDialog({
  targetBridge,
  open,
  onOpenChange,
  onMerged,
}: BridgeMergeDialogProps) {
  const [searchTerm, setSearchTerm] = useState("")
  const [results, setResults] = useState<BridgeListItem[]>([])
  const [selectedBridge, setSelectedBridge] = useState<BridgeListItem | null>(
    null,
  )
  const [isMerging, setIsMerging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounced search
  const doSearch = useCallback(
    (term: string) => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
      if (!term.trim()) {
        setResults([])
        return
      }
      debounceRef.current = setTimeout(async () => {
        try {
          const data = await fetchBridges({ q: term, page_size: 10 })
          // Exclude the current target bridge from results
          setResults(
            data.items.filter((b) => b.id !== targetBridge.id),
          )
        } catch {
          // Silently ignore search errors
        }
      }, 300)
    },
    [targetBridge.id],
  )

  useEffect(() => {
    doSearch(searchTerm)
  }, [searchTerm, doSearch])

  // Reset state when dialog opens/closes
  useEffect(() => {
    if (!open) {
      setSearchTerm("")
      setResults([])
      setSelectedBridge(null)
      setError(null)
    }
  }, [open])

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  const handleConfirm = async () => {
    if (!selectedBridge) return
    setIsMerging(true)
    setError(null)
    try {
      await mergeBridge(targetBridge.id, {
        source_bridge_id: selectedBridge.id,
      })
      onMerged()
      onOpenChange(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsMerging(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>合并桥梁</DialogTitle>
          <DialogDescription>
            选择要合并到「{targetBridge.name}」的源桥梁
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Search input */}
          <Input
            placeholder="搜索桥梁名称..."
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value)
              setSelectedBridge(null)
            }}
          />

          {/* Search results */}
          {results.length > 0 && !selectedBridge && (
            <div className="max-h-48 overflow-y-auto rounded-md border">
              {results.map((b) => (
                <button
                  key={b.id}
                  type="button"
                  className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                  onClick={() => setSelectedBridge(b)}
                >
                  <span className="font-medium">{b.name}</span>
                  <span className="ml-2 text-muted-foreground">
                    ({b.chunk_count} 个知识块)
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Preview info when a bridge is selected */}
          {selectedBridge && (
            <div className="space-y-2 rounded-md border p-3">
              <p className="text-sm">
                源桥梁: 「{selectedBridge.name}」({selectedBridge.chunk_count}{" "}
                个知识块)
              </p>
              <p className="text-sm">
                将被合并到: 「{targetBridge.name}」
              </p>
              <p className="text-sm font-medium text-destructive">
                此操作不可逆，源桥梁将被删除
              </p>
            </div>
          )}

          {/* Error message */}
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={!selectedBridge || isMerging}
          >
            {isMerging ? "合并中..." : "确认合并"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
