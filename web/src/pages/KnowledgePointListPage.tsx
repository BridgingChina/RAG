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
import { Pagination } from "@/components/Pagination"
import { useApi } from "@/hooks/useApi"
import {
  autoAssociateChunks,
  createKnowledgePoint,
  fetchKnowledgePoints,
  fetchTaxonomyTree,
} from "@/lib/api"

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
  const [newLvl1, setNewLvl1] = useState("")
  const [newLvl2, setNewLvl2] = useState("")
  const [newDifficulty, setNewDifficulty] = useState("")
  const [createStatusMsg, setCreateStatusMsg] = useState<string | null>(null)

  const { data, loading, error, refetch } = useApi(
    () => fetchKnowledgePoints({ page, page_size: 20 }),
    [page],
  )

  const { data: taxonomyTree } = useApi(() => fetchTaxonomyTree(), [])

  // Phase 3: tree has 3 layers (lvl1 → lvl2 → KP). Build lvl1 / lvl2
  // option lists for the create dialog and a (node_id → label) map used
  // when rendering the KP list (the label is the KP's own name at L3).
  const lvl1Options: string[] = []
  const lvl2ByLvl1 = new Map<string, string[]>()
  const taxonomyLabelMap = new Map<string, string>()
  if (taxonomyTree) {
    for (const l1 of taxonomyTree.items) {
      lvl1Options.push(l1.label)
      lvl2ByLvl1.set(l1.label, l1.children.map((l2) => l2.label))
      for (const l2 of l1.children) {
        for (const kp of l2.children) {
          taxonomyLabelMap.set(kp.node_id, kp.label)
        }
      }
    }
  }
  const lvl2Options = newLvl1 ? (lvl2ByLvl1.get(newLvl1) ?? []) : []

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    setCreateError(null)
    setCreateStatusMsg(null)
    try {
      const kp = await createKnowledgePoint({
        name: newName.trim(),
        lvl1: newLvl1 || undefined,
        lvl2: newLvl2 || undefined,
        difficulty: newDifficulty || undefined,
      })
      // Auto-associate chunks under the same (lvl1, lvl2) via LLM.
      // Skip if lvl1/lvl2 not set (endpoint would 422).
      if (newLvl1 && newLvl2) {
        setCreateStatusMsg("AI 正在关联同分类下的知识块…")
        try {
          const r = await autoAssociateChunks(kp.id)
          setCreateStatusMsg(
            `关联完成：扫描 ${r.candidate_count} 条候选，命中 ${r.matched_chunk_ids.length} 条。`,
          )
        } catch (e) {
          setCreateStatusMsg(
            `KP 已创建，但自动关联失败：${e instanceof Error ? e.message : String(e)}。稍后可在详情页重试。`,
          )
        }
      }
      setIsCreateOpen(false)
      setNewName("")
      setNewLvl1("")
      setNewLvl2("")
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

            <Pagination page={page} totalPages={total_pages} onPageChange={setPage} />
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
              <Label>一级分类</Label>
              <Select
                value={newLvl1 || "__none__"}
                onValueChange={(v) => {
                  const val = v === "__none__" ? "" : v
                  setNewLvl1(val)
                  setNewLvl2("")
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择一级分类..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">不选择</SelectItem>
                  {lvl1Options.map((l) => (
                    <SelectItem key={l} value={l}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>二级分类</Label>
              <Select
                value={newLvl2 || "__none__"}
                onValueChange={(v) => setNewLvl2(v === "__none__" ? "" : v)}
                disabled={!newLvl1}
              >
                <SelectTrigger>
                  <SelectValue placeholder={newLvl1 ? "选择二级分类..." : "请先选一级分类"} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">不选择</SelectItem>
                  {lvl2Options.map((l) => (
                    <SelectItem key={l} value={l}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                填写分类后，创建成功会自动 LLM 扫描同分类下未挂载的知识块并关联。
              </p>
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
            {createStatusMsg && (
              <p className="text-sm text-muted-foreground">{createStatusMsg}</p>
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
