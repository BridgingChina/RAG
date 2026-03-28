import { useState } from "react"
import { useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useApi } from "@/hooks/useApi"
import { fetchKnowledgePoints, createKnowledgePoint, fetchTaxonomyTree } from "@/lib/api"

const DIFFICULTY_OPTIONS = [
  { value: "basic", label: "基础" },
  { value: "intermediate", label: "中级" },
  { value: "advanced", label: "高级" },
]

function difficultyLabel(d: string | null) {
  if (!d) return null
  const opt = DIFFICULTY_OPTIONS.find((o) => o.value === d)
  return opt ? opt.label : d
}

export function Component() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [newName, setNewName] = useState("")
  const [newTaxonomyNodeId, setNewTaxonomyNodeId] = useState("")
  const [newDifficulty, setNewDifficulty] = useState("")

  const { data, loading, error, refetch } = useApi(
    () => fetchKnowledgePoints({ page, page_size: 20 }),
    [page],
  )

  const { data: taxonomyTree } = useApi(() => fetchTaxonomyTree(), [])

  // Flatten taxonomy tree to get lvl3 nodes for the select
  const taxonomyOptions: Array<{ id: string; label: string }> = []
  if (taxonomyTree) {
    for (const l1 of taxonomyTree.items) {
      for (const l2 of l1.children) {
        for (const l3 of l2.children) {
          taxonomyOptions.push({
            id: l3.node_id,
            label: `${l1.label} / ${l2.label} / ${l3.label}`,
          })
        }
      }
    }
  }

  // Build a map of taxonomy_node_id → label for display
  const taxonomyLabelMap = new Map<string, string>()
  if (taxonomyTree) {
    for (const l1 of taxonomyTree.items) {
      for (const l2 of l1.children) {
        for (const l3 of l2.children) {
          taxonomyLabelMap.set(l3.node_id, l3.label)
        }
      }
    }
  }

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      const kp = await createKnowledgePoint({
        name: newName.trim(),
        taxonomy_node_id: newTaxonomyNodeId || undefined,
        difficulty: newDifficulty || undefined,
      })
      setIsCreateOpen(false)
      setNewName("")
      setNewTaxonomyNodeId("")
      setNewDifficulty("")
      navigate(`/knowledge-points/${kp.id}`)
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e))
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return (
      <>
        <PageHeader title="知识点管理" description="浏览和管理知识点">
          <Button disabled>新建知识点</Button>
        </PageHeader>
        <main className="space-y-6 p-6">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-96 w-full" />
        </main>
      </>
    )
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="知识点管理" description="浏览和管理知识点">
          <Button onClick={() => setIsCreateOpen(true)}>新建知识点</Button>
        </PageHeader>
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{error || "加载失败"}</p>
            <Button onClick={refetch} variant="outline" size="sm">
              重试
            </Button>
          </div>
        </main>
      </>
    )
  }

  const { items, total_pages } = data
  const hasNext = total_pages > 0 && page < total_pages
  const hasPrev = page > 1

  return (
    <>
      <PageHeader title="知识点管理" description="浏览和管理知识点">
        <Button onClick={() => setIsCreateOpen(true)}>新建知识点</Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">暂无知识点数据</p>
          </div>
        ) : (
          <>
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead>
                    <TableHead>难度</TableHead>
                    <TableHead>分类</TableHead>
                    <TableHead>摘要</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((kp) => (
                    <TableRow
                      key={kp.id}
                      className="cursor-pointer"
                      onClick={() => navigate(`/knowledge-points/${kp.id}`)}
                    >
                      <TableCell className="font-medium">{kp.name}</TableCell>
                      <TableCell>
                        {kp.difficulty ? (
                          <Badge variant="secondary">
                            {difficultyLabel(kp.difficulty)}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {kp.taxonomy_node_id ? (
                          taxonomyLabelMap.get(kp.taxonomy_node_id) || kp.taxonomy_node_id
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-md truncate">
                        {kp.summary || (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            {total_pages > 0 && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  第 {page} / {total_pages} 页
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page - 1)}
                    disabled={!hasPrev}
                  >
                    上一页
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page + 1)}
                    disabled={!hasNext}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新建知识点</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>名称 *</Label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="知识点名称"
              />
            </div>
            <div className="space-y-2">
              <Label>分类节点</Label>
              <Select value={newTaxonomyNodeId} onValueChange={setNewTaxonomyNodeId}>
                <SelectTrigger>
                  <SelectValue placeholder="选择分类..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">不选择</SelectItem>
                  {taxonomyOptions.map((opt) => (
                    <SelectItem key={opt.id} value={opt.id}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>难度</Label>
              <Select value={newDifficulty} onValueChange={setNewDifficulty}>
                <SelectTrigger>
                  <SelectValue placeholder="选择难度..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">不选择</SelectItem>
                  {DIFFICULTY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {createError && (
              <p className="text-sm text-destructive">{createError}</p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              取消
            </Button>
            <Button
              onClick={handleCreate}
              disabled={creating || !newName.trim()}
            >
              {creating ? "创建中..." : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
