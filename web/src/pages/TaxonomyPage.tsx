import { useState } from "react"
import { useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { TaxonomyTree } from "@/components/taxonomy/TaxonomyTree"
import { useApi } from "@/hooks/useApi"
import {
  fetchTaxonomyTree,
  fetchChunks,
  createTaxonomyNode,
  deleteTaxonomyNode,
  batchUpdateTaxonomy,
} from "@/lib/api"

// Helper function for binding status badge variant
function getBindingVariant(status: string) {
  if (status === "primary") return "default"
  if (status === "ambiguous") return "destructive"
  return "secondary"
}

// Helper function for binding status label
function getBindingLabel(status: string) {
  if (status === "primary") return "绑定"
  if (status === "ambiguous") return "歧义"
  return "未绑定"
}

export function Component() {
  const navigate = useNavigate()
  const [selectedPath, setSelectedPath] = useState<{
    lvl1: string
    lvl2?: string
    lvl3?: string
  } | null>(null)
  const [selectedChunkIds, setSelectedChunkIds] = useState<Set<number>>(new Set())
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ nodeId: number; label: string } | null>(null)
  const [isBatchUpdateDialogOpen, setIsBatchUpdateDialogOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Add node form state
  const [newNodeLvl1, setNewNodeLvl1] = useState("")
  const [newNodeLvl2, setNewNodeLvl2] = useState("")
  const [newNodeLvl3, setNewNodeLvl3] = useState("")
  const [newNodeDescription, setNewNodeDescription] = useState("")
  const [parentForAdd, setParentForAdd] = useState<{ lvl1: string; lvl2?: string } | null>(null)

  // Batch update form state
  const [batchLvl1, setBatchLvl1] = useState("")
  const [batchLvl2, setBatchLvl2] = useState("")
  const [batchLvl3, setBatchLvl3] = useState("")

  // Fetch taxonomy tree
  const { data: treeData, loading: treeLoading, error: treeError, refetch: refetchTree } = useApi(
    fetchTaxonomyTree,
    [],
  )

  // Fetch chunks for selected node
  const { data: chunksData, loading: chunksLoading, refetch: refetchChunks } = useApi(
    () => {
      if (!selectedPath) {
        return Promise.resolve({ items: [], total: 0, page: 1, page_size: 100, total_pages: 0 })
      }
      return fetchChunks({
        lvl1: selectedPath.lvl1,
        lvl2: selectedPath.lvl2,
        lvl3: selectedPath.lvl3,
        page: 1,
        page_size: 100,
      })
    },
    [selectedPath],
  )

  const handleSelectNode = (path: { lvl1: string; lvl2?: string; lvl3?: string }) => {
    setSelectedPath(path)
    setSelectedChunkIds(new Set())
  }

  const handleAddNode = (parent: { lvl1: string; lvl2?: string }) => {
    setParentForAdd(parent)
    setNewNodeLvl1(parent.lvl1)
    setNewNodeLvl2(parent.lvl2 || "")
    setNewNodeLvl3("")
    setNewNodeDescription("")
    setIsAddDialogOpen(true)
  }

  const handleDeleteNode = (nodeId: number, nodeLabel: string) => {
    setDeleteTarget({ nodeId, label: nodeLabel })
    setActionError(null)
    setIsDeleteDialogOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setIsSubmitting(true)
    setActionError(null)
    try {
      await deleteTaxonomyNode(deleteTarget.nodeId)
      refetchTree()
      setIsDeleteDialogOpen(false)
      setDeleteTarget(null)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSubmitAddNode = async () => {
    setIsSubmitting(true)
    setActionError(null)
    try {
      await createTaxonomyNode({
        lvl1: newNodeLvl1,
        lvl2: newNodeLvl2 || null,
        lvl3: newNodeLvl3 || null,
        description: newNodeDescription || null,
      })
      refetchTree()
      setIsAddDialogOpen(false)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleToggleChunk = (chunkId: number) => {
    const newSet = new Set(selectedChunkIds)
    if (newSet.has(chunkId)) {
      newSet.delete(chunkId)
    } else {
      newSet.add(chunkId)
    }
    setSelectedChunkIds(newSet)
  }

  const handleToggleAll = () => {
    const chunks = chunksData?.items || []
    if (selectedChunkIds.size === chunks.length) {
      setSelectedChunkIds(new Set())
    } else {
      setSelectedChunkIds(new Set(chunks.map((c) => c.id)))
    }
  }

  const handleOpenBatchUpdate = () => {
    setBatchLvl1("")
    setBatchLvl2("")
    setBatchLvl3("")
    setIsBatchUpdateDialogOpen(true)
  }

  const handleSubmitBatchUpdate = async () => {
    if (!batchLvl1) {
      setActionError("请选择一级分类")
      return
    }

    setIsSubmitting(true)
    setActionError(null)
    try {
      await batchUpdateTaxonomy({
        chunk_ids: Array.from(selectedChunkIds),
        lvl1: batchLvl1,
        lvl2: batchLvl2 || null,
        lvl3: batchLvl3 || null,
      })
      refetchTree()
      refetchChunks()
      setSelectedChunkIds(new Set())
      setIsBatchUpdateDialogOpen(false)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsSubmitting(false)
    }
  }

  // Extract unique lvl1/lvl2/lvl3 options from tree for batch update
  const lvl1Options = treeData?.items.map((item) => item.label) || []
  const lvl2Options =
    (batchLvl1 && treeData?.items.find((item) => item.label === batchLvl1)?.children.map((item) => item.label)) || []
  const lvl3Options =
    (batchLvl2 &&
      treeData?.items
        .find((item) => item.label === batchLvl1)
        ?.children.find((item) => item.label === batchLvl2)
        ?.children.map((item) => item.label)) ||
    []

  const chunks = chunksData?.items || []
  const hasSelectedChunks = selectedChunkIds.size > 0

  if (treeLoading) {
    return (
      <>
        <PageHeader title="分类目录" description="知识分类体系管理" />
        <main className="p-6">
          <Skeleton className="h-96 w-full" />
        </main>
      </>
    )
  }

  if (treeError || !treeData) {
    return (
      <>
        <PageHeader title="分类目录" description="知识分类体系管理" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{treeError || "加载失败"}</p>
            <Button onClick={refetchTree} variant="outline" size="sm">
              重试
            </Button>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader title="分类目录" description="知识分类体系管理" />

      <main className="p-6">
        <div className="flex gap-6 h-[calc(100vh-12rem)]">
          {/* Left panel: Tree (1/3) */}
          <Card className="w-1/3 flex flex-col">
            <CardContent className="flex-1 overflow-auto p-4">
              <TaxonomyTree
                items={treeData.items}
                selectedPath={selectedPath || undefined}
                onSelect={handleSelectNode}
                onAddNode={handleAddNode}
                onDeleteNode={handleDeleteNode}
              />
            </CardContent>
            <div className="p-4 border-t">
              <Button
                onClick={() => {
                  setParentForAdd(null)
                  setNewNodeLvl1("")
                  setNewNodeLvl2("")
                  setNewNodeLvl3("")
                  setNewNodeDescription("")
                  setIsAddDialogOpen(true)
                }}
                variant="outline"
                className="w-full"
              >
                新增一级分类
              </Button>
            </div>
          </Card>

          {/* Right panel: Chunks (2/3) */}
          <Card className="flex-1 flex flex-col">
            <CardContent className="flex-1 overflow-auto p-4">
              {!selectedPath ? (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  选择左侧分类查看知识块
                </div>
              ) : chunksLoading ? (
                <Skeleton className="h-full w-full" />
              ) : chunks.length === 0 ? (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  该分类下暂无知识块
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Checkbox
                        checked={selectedChunkIds.size === chunks.length && chunks.length > 0}
                        onCheckedChange={handleToggleAll}
                      />
                      <span className="text-sm text-muted-foreground">
                        已选 {selectedChunkIds.size} / {chunks.length}
                      </span>
                    </div>
                    {hasSelectedChunks && (
                      <Button onClick={handleOpenBatchUpdate} size="sm">
                        批量修改分类
                      </Button>
                    )}
                  </div>

                  <div className="rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-12"></TableHead>
                          <TableHead>内容预览</TableHead>
                          <TableHead>绑定状态</TableHead>
                          <TableHead>来源</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {chunks.map((chunk) => (
                          <TableRow key={chunk.id}>
                            <TableCell onClick={(e) => e.stopPropagation()}>
                              <Checkbox
                                checked={selectedChunkIds.has(chunk.id)}
                                onCheckedChange={() => handleToggleChunk(chunk.id)}
                              />
                            </TableCell>
                            <TableCell
                              className="max-w-md truncate cursor-pointer"
                              onClick={() => navigate(`/chunks/${chunk.id}`)}
                            >
                              {chunk.content_preview}
                            </TableCell>
                            <TableCell>
                              <Badge variant={getBindingVariant(chunk.binding_status)}>
                                {getBindingLabel(chunk.binding_status)}
                              </Badge>
                            </TableCell>
                            <TableCell>
                              {chunk.source_title || (
                                <span className="text-muted-foreground">未命名来源</span>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      {/* Add Node Dialog */}
      <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新增分类</DialogTitle>
            <DialogDescription>
              {parentForAdd
                ? `在「${parentForAdd.lvl1}${parentForAdd.lvl2 ? " / " + parentForAdd.lvl2 : ""}」下新增子分类`
                : "新增一级分类"}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">一级分类</label>
              <Input
                value={newNodeLvl1}
                onChange={(e) => setNewNodeLvl1(e.target.value)}
                disabled={!!parentForAdd}
                placeholder="例如：形制与技术"
              />
            </div>
            {parentForAdd && (
              <div>
                <label className="text-sm font-medium">
                  {parentForAdd.lvl2 ? "三级分类" : "二级分类"}
                </label>
                <Input
                  value={parentForAdd.lvl2 ? newNodeLvl3 : newNodeLvl2}
                  onChange={(e) =>
                    parentForAdd.lvl2 ? setNewNodeLvl3(e.target.value) : setNewNodeLvl2(e.target.value)
                  }
                  placeholder={parentForAdd.lvl2 ? "例如：拱桥结构" : "例如：结构体系"}
                />
              </div>
            )}
            <div>
              <label className="text-sm font-medium">描述（可选）</label>
              <Input
                value={newNodeDescription}
                onChange={(e) => setNewNodeDescription(e.target.value)}
                placeholder="分类说明"
              />
            </div>
            {actionError && <p className="text-sm text-destructive">{actionError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleSubmitAddNode} disabled={isSubmitting || !newNodeLvl1}>
              {isSubmitting ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Batch Update Dialog */}
      <Dialog open={isBatchUpdateDialogOpen} onOpenChange={setIsBatchUpdateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>批量修改分类</DialogTitle>
            <DialogDescription>为选中的 {selectedChunkIds.size} 个知识块设置分类</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">一级分类</label>
              <Select value={batchLvl1} onValueChange={(v) => { setBatchLvl1(v); setBatchLvl2(""); setBatchLvl3("") }}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="选择一级分类" />
                </SelectTrigger>
                <SelectContent>
                  {lvl1Options.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {batchLvl1 && lvl2Options.length > 0 && (
              <div>
                <label className="text-sm font-medium">二级分类（可选）</label>
                <Select value={batchLvl2} onValueChange={(v) => { setBatchLvl2(v); setBatchLvl3("") }}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="选择二级分类" />
                  </SelectTrigger>
                  <SelectContent>
                    {lvl2Options.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {batchLvl2 && lvl3Options.length > 0 && (
              <div>
                <label className="text-sm font-medium">三级分类（可选）</label>
                <Select value={batchLvl3} onValueChange={setBatchLvl3}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="选择三级分类" />
                  </SelectTrigger>
                  <SelectContent>
                    {lvl3Options.map((opt) => (
                      <SelectItem key={opt} value={opt}>
                        {opt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            {actionError && <p className="text-sm text-destructive">{actionError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsBatchUpdateDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleSubmitBatchUpdate} disabled={isSubmitting || !batchLvl1}>
              {isSubmitting ? "更新中..." : "确认修改"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除分类「{deleteTarget?.label}」吗？仅当该分类下无关联知识块时可删除。
            </DialogDescription>
          </DialogHeader>
          {actionError && (
            <p className="text-sm text-destructive">{actionError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDeleteDialogOpen(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleConfirmDelete} disabled={isSubmitting}>
              {isSubmitting ? "删除中..." : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
