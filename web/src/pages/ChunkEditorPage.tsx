import { useCallback, useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { useApi } from "@/hooks/useApi"
import { fetchChunks, fetchSource, fetchTaxonomyTree, reindexSource } from "@/lib/api"
import type { ChunkListItem } from "@/lib/types"
import { ArrowLeft, RefreshCw, Loader2 } from "lucide-react"
import { staleCount } from "@/components/chunk-editor/types"
import { ChunkItem } from "@/components/chunk-editor/ChunkItem"
import { ChunkEditor } from "@/components/chunk-editor/ChunkEditor"
import { BatchToolbar } from "@/components/chunk-editor/BatchToolbar"

export function Component() {
  const { sourceId } = useParams()
  const navigate = useNavigate()
  const sid = sourceId!

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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set())

  // Reindex state
  const [reindexing, setReindexing] = useState(false)
  const [reindexError, setReindexError] = useState<string | null>(null)

  // Sort ascending by created_at (UUID ids have no meaningful order)
  const chunks: ChunkListItem[] = [...(chunksData?.items ?? [])].sort(
    (a, b) => a.created_at.localeCompare(b.created_at),
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

  function toggleCheck(id: string, checked: boolean) {
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
            <Badge className="ml-1 bg-[var(--yellow-hemp)] text-[var(--ink-black)] text-xs px-1.5 py-0">
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
        <aside className="flex w-80 shrink-0 flex-col border-r bg-background">
          <div className="border-b px-3 py-2 text-xs text-muted-foreground">
            {chunksLoading
              ? "加载中…"
              : `共 ${chunksData?.total ?? chunks.length} 个块${stale > 0 ? `，${stale} 待索引` : ""}`}
            {!chunksLoading && chunksData && chunksData.total > chunks.length && (
              <span className="ml-1 text-[var(--yellow-hemp)]">
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
              <p className="p-4 text-xs text-muted-foreground">暂无知识块</p>
            )}
          </div>
        </aside>

        {/* Right pane */}
        <main className="flex-1 overflow-hidden bg-muted/20">
          {selectedId !== null ? (
            <ChunkEditor
              key={selectedId}
              chunkId={selectedId}
              onMutated={handleMutated}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
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
