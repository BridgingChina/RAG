import { useState } from "react"
import { useParams, useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
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
  fetchKnowledgePoint,
  updateKnowledgePoint,
  deleteKnowledgePoint,
  generateKeyPoints,
  generateFlashcards,
  syncKPBridges,
  fetchKPBridges,
  replaceKPBridges,
  fetchTaxonomyTree,
} from "@/lib/api"
import type { L2Content, KPBridgeItem } from "@/lib/types"

const DIFFICULTY_OPTIONS = [
  { value: "basic", label: "基础" },
  { value: "intermediate", label: "中级" },
  { value: "advanced", label: "高级" },
]

export function Component() {
  const { id } = useParams()
  const navigate = useNavigate()

  // Basic info form state
  const [editName, setEditName] = useState("")
  const [editAliases, setEditAliases] = useState("")
  const [editDifficulty, setEditDifficulty] = useState("")
  const [editSummary, setEditSummary] = useState("")
  const [editTaxonomyNodeId, setEditTaxonomyNodeId] = useState("")
  const [basicSaving, setBasicSaving] = useState(false)
  const [basicError, setBasicError] = useState<string | null>(null)
  const [basicSuccess, setBasicSuccess] = useState(false)
  const [formInitialized, setFormInitialized] = useState(false)

  // Key points
  const [generatingKP, setGeneratingKP] = useState(false)
  const [kpError, setKpError] = useState<string | null>(null)
  const [kpSuccess, setKpSuccess] = useState<string | null>(null)
  const [generatingFC, setGeneratingFC] = useState(false)
  const [fcError, setFcError] = useState<string | null>(null)
  const [fcSuccess, setFcSuccess] = useState<string | null>(null)

  // Bridges
  const [syncing, setSyncing] = useState(false)
  const [bridgeError, setBridgeError] = useState<string | null>(null)
  const [bridgeSuccess, setBridgeSuccess] = useState<string | null>(null)
  const [editingBridgeNotes, setEditingBridgeNotes] = useState<Map<string, string>>(new Map())

  // L2 content
  const [l2, setL2] = useState<L2Content>({})
  const [l2Initialized, setL2Initialized] = useState(false)
  const [l2Saving, setL2Saving] = useState(false)
  const [l2Error, setL2Error] = useState<string | null>(null)
  const [l2Success, setL2Success] = useState(false)

  // Delete
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const { data: kp, loading, error, refetch } = useApi(
    () => fetchKnowledgePoint(id!),
    [id],
  )

  const { data: bridgesData, refetch: refetchBridges } = useApi(
    () => fetchKPBridges(id!),
    [id],
  )

  const { data: taxonomyTree } = useApi(() => fetchTaxonomyTree(), [])

  // Initialize form when data loads
  if (kp && !formInitialized) {
    setEditName(kp.name)
    setEditAliases(kp.aliases || "")
    setEditDifficulty(kp.difficulty || "")
    setEditSummary(kp.summary || "")
    setEditTaxonomyNodeId(kp.taxonomy_node_id || "")
    setFormInitialized(true)
  }

  if (kp && !l2Initialized) {
    setL2(kp.l2_content || {})
    setL2Initialized(true)
  }

  // Flatten taxonomy tree to get lvl3 nodes
  const taxonomyOptions: Array<{ id: string; label: string }> = []
  if (taxonomyTree) {
    for (const l1 of taxonomyTree.items) {
      for (const l2Node of l1.children) {
        for (const l3 of l2Node.children) {
          taxonomyOptions.push({
            id: l3.node_id,
            label: `${l1.label} / ${l2Node.label} / ${l3.label}`,
          })
        }
      }
    }
  }

  const bridges: KPBridgeItem[] = bridgesData?.items || []

  // --- Handlers ---

  const handleSaveBasicInfo = async () => {
    if (!id) return
    setBasicSaving(true)
    setBasicError(null)
    setBasicSuccess(false)
    try {
      await updateKnowledgePoint(id, {
        name: editName.trim(),
        aliases: editAliases.trim() || null,
        difficulty: editDifficulty || null,
        summary: editSummary.trim() || null,
        taxonomy_node_id: (editTaxonomyNodeId && editTaxonomyNodeId !== "__none__")
          ? editTaxonomyNodeId
          : null,
      })
      setBasicSuccess(true)
      refetch()
      setTimeout(() => setBasicSuccess(false), 2000)
    } catch (e) {
      setBasicError(e instanceof Error ? e.message : String(e))
    } finally {
      setBasicSaving(false)
    }
  }

  const handleGenerateKeyPoints = async () => {
    if (!id) return
    setGeneratingKP(true)
    setKpError(null)
    setKpSuccess(null)
    try {
      const result = await generateKeyPoints(id)
      setKpSuccess(`已生成 ${result.generated} 个要点`)
      refetch()
    } catch (e) {
      setKpError(e instanceof Error ? e.message : String(e))
    } finally {
      setGeneratingKP(false)
    }
  }

  const handleGenerateFlashcards = async () => {
    if (!id) return
    setGeneratingFC(true)
    setFcError(null)
    setFcSuccess(null)
    try {
      const result = await generateFlashcards(id)
      const msg = `已生成 ${result.generated} 张闪卡`
      if (result.errors?.length > 0) {
        setFcSuccess(`${msg}，${result.errors.length} 个错误`)
      } else {
        setFcSuccess(msg)
      }
    } catch (e) {
      setFcError(e instanceof Error ? e.message : String(e))
    } finally {
      setGeneratingFC(false)
    }
  }

  const handleSyncBridges = async () => {
    if (!id) return
    setSyncing(true)
    setBridgeError(null)
    setBridgeSuccess(null)
    try {
      const result = await syncKPBridges(id)
      setBridgeSuccess(`已同步 ${result.synced} 个关联`)
      refetchBridges()
    } catch (e) {
      setBridgeError(e instanceof Error ? e.message : String(e))
    } finally {
      setSyncing(false)
    }
  }

  const handleRemoveBridge = async (bridgeId: string) => {
    if (!id) return
    setBridgeError(null)
    try {
      const remaining = bridges
        .filter((b) => b.bridge_id !== bridgeId)
        .map((b, idx) => ({
          bridge_id: b.bridge_id,
          relevance_note: editingBridgeNotes.get(b.bridge_id) ?? b.relevance_note ?? undefined,
          order_index: idx,
        }))
      await replaceKPBridges(id, remaining)
      refetchBridges()
    } catch (e) {
      setBridgeError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleSaveBridgeNotes = async () => {
    if (!id || editingBridgeNotes.size === 0) return
    setBridgeError(null)
    setBridgeSuccess(null)
    try {
      const items = bridges.map((b, idx) => ({
        bridge_id: b.bridge_id,
        relevance_note: editingBridgeNotes.has(b.bridge_id)
          ? (editingBridgeNotes.get(b.bridge_id) || undefined)
          : (b.relevance_note ?? undefined),
        order_index: idx,
      }))
      await replaceKPBridges(id, items)
      setBridgeSuccess("备注已保存")
      setEditingBridgeNotes(new Map())
      refetchBridges()
      setTimeout(() => setBridgeSuccess(null), 2000)
    } catch (e) {
      setBridgeError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleSaveL2 = async () => {
    if (!id) return
    setL2Saving(true)
    setL2Error(null)
    setL2Success(false)
    try {
      // Clean empty arrays
      const cleaned: L2Content = {}
      if (l2.comparisons && l2.comparisons.length > 0) {
        cleaned.comparisons = l2.comparisons.filter((c) => c.title.trim() || c.content.trim())
      }
      if (l2.evolution?.trim()) {
        cleaned.evolution = l2.evolution.trim()
      }
      if (l2.controversies && l2.controversies.length > 0) {
        cleaned.controversies = l2.controversies.filter(
          (c) => c.title.trim() || c.description.trim(),
        )
      }
      if (l2.further_reading && l2.further_reading.length > 0) {
        cleaned.further_reading = l2.further_reading.filter((r) => r.title.trim())
      }
      const hasContent = Object.keys(cleaned).length > 0
      await updateKnowledgePoint(id, { l2_content: hasContent ? cleaned : null })
      setL2Success(true)
      refetch()
      setTimeout(() => setL2Success(false), 2000)
    } catch (e) {
      setL2Error(e instanceof Error ? e.message : String(e))
    } finally {
      setL2Saving(false)
    }
  }

  const handleDelete = async () => {
    if (!id) return
    setIsDeleting(true)
    setDeleteError(null)
    try {
      await deleteKnowledgePoint(id)
      navigate("/knowledge-points")
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e))
      setIsDeleteDialogOpen(false)
    } finally {
      setIsDeleting(false)
    }
  }

  // --- L2 helpers ---

  const updateComparison = (idx: number, field: "title" | "content", value: string) => {
    setL2((prev) => {
      const comparisons = [...(prev.comparisons || [])]
      comparisons[idx] = { ...comparisons[idx], [field]: value }
      return { ...prev, comparisons }
    })
  }

  const addComparison = () => {
    setL2((prev) => ({
      ...prev,
      comparisons: [...(prev.comparisons || []), { title: "", content: "" }],
    }))
  }

  const removeComparison = (idx: number) => {
    setL2((prev) => ({
      ...prev,
      comparisons: (prev.comparisons || []).filter((_, i) => i !== idx),
    }))
  }

  const updateControversy = (idx: number, field: "title" | "description", value: string) => {
    setL2((prev) => {
      const controversies = [...(prev.controversies || [])]
      controversies[idx] = { ...controversies[idx], [field]: value }
      return { ...prev, controversies }
    })
  }

  const addControversy = () => {
    setL2((prev) => ({
      ...prev,
      controversies: [...(prev.controversies || []), { title: "", description: "" }],
    }))
  }

  const removeControversy = (idx: number) => {
    setL2((prev) => ({
      ...prev,
      controversies: (prev.controversies || []).filter((_, i) => i !== idx),
    }))
  }

  const updateFurtherReading = (idx: number, value: string) => {
    setL2((prev) => {
      const further_reading = [...(prev.further_reading || [])]
      further_reading[idx] = { ...further_reading[idx], title: value }
      return { ...prev, further_reading }
    })
  }

  const addFurtherReading = () => {
    setL2((prev) => ({
      ...prev,
      further_reading: [...(prev.further_reading || []), { title: "" }],
    }))
  }

  const removeFurtherReading = (idx: number) => {
    setL2((prev) => ({
      ...prev,
      further_reading: (prev.further_reading || []).filter((_, i) => i !== idx),
    }))
  }

  // --- Render ---

  if (loading) {
    return (
      <>
        <PageHeader title="知识点详情" />
        <main className="space-y-6 p-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-48 w-full" />
        </main>
      </>
    )
  }

  if (error || !kp) {
    return (
      <>
        <PageHeader title="知识点详情" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{error || "未找到知识点"}</p>
            <Button onClick={() => navigate("/knowledge-points")} variant="outline">
              返回列表
            </Button>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader title="知识点详情">
        <Button onClick={() => navigate("/knowledge-points")} variant="outline">
          返回列表
        </Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {/* Card 1: Basic Info */}
        <Card>
          <CardHeader>
            <CardTitle>基本信息</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>名称 *</Label>
                <Input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>别名</Label>
                <Input
                  value={editAliases}
                  onChange={(e) => setEditAliases(e.target.value)}
                  placeholder="逗号分隔的别名"
                />
              </div>
              <div className="space-y-2">
                <Label>难度</Label>
                <Select
                  value={editDifficulty || "__none__"}
                  onValueChange={(v) => setEditDifficulty(v === "__none__" ? "" : v)}
                >
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
              <div className="space-y-2">
                <Label>分类节点</Label>
                <Select
                  value={editTaxonomyNodeId || "__none__"}
                  onValueChange={(v) => setEditTaxonomyNodeId(v === "__none__" ? "" : v)}
                >
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
            </div>
            <div className="space-y-2">
              <Label>摘要</Label>
              <Textarea
                value={editSummary}
                onChange={(e) => setEditSummary(e.target.value)}
                rows={3}
                placeholder="知识点摘要..."
              />
            </div>
            {basicError && <p className="text-sm text-destructive">{basicError}</p>}
            {basicSuccess && <p className="text-sm text-green-600">已保存</p>}
            <Button onClick={handleSaveBasicInfo} disabled={basicSaving || !editName.trim()}>
              {basicSaving ? "保存中..." : "保存基本信息"}
            </Button>
          </CardContent>
        </Card>

        {/* Card 2: Key Points */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>核心要点</CardTitle>
              <Badge variant="secondary">{kp.key_points.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {kp.key_points.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无要点，点击下方按钮生成</p>
            ) : (
              <div className="space-y-3">
                {kp.key_points
                  .sort((a, b) => a.order_index - b.order_index)
                  .map((point, idx) => (
                    <div key={point.id} className="rounded-lg border p-3">
                      <div className="flex items-start gap-2">
                        <Badge variant="outline" className="mt-0.5 shrink-0">
                          {idx + 1}
                        </Badge>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium">{point.summary}</p>
                          {point.explanation && (
                            <p className="mt-1 text-sm text-muted-foreground">
                              {point.explanation}
                            </p>
                          )}
                          {point.chunk_ids.length > 0 && (
                            <p className="mt-1 text-xs text-muted-foreground">
                              关联 {point.chunk_ids.length} 个知识块
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={handleGenerateKeyPoints}
                disabled={generatingKP}
              >
                {generatingKP ? "生成中..." : "生成要点"}
              </Button>
              <Button
                variant="outline"
                onClick={handleGenerateFlashcards}
                disabled={generatingFC}
              >
                {generatingFC ? "生成中..." : "生成闪卡"}
              </Button>
            </div>
            {kpError && <p className="text-sm text-destructive">{kpError}</p>}
            {kpSuccess && <p className="text-sm text-green-600">{kpSuccess}</p>}
            {fcError && <p className="text-sm text-destructive">{fcError}</p>}
            {fcSuccess && <p className="text-sm text-green-600">{fcSuccess}</p>}
          </CardContent>
        </Card>

        {/* Card 3: Associated Bridges */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>关联桥梁</CardTitle>
              <Badge variant="secondary">{bridges.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {bridges.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无关联桥梁</p>
            ) : (
              <div className="space-y-2">
                {bridges.map((b) => (
                  <div
                    key={b.id}
                    className="flex items-center gap-3 rounded-lg border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{b.bridge_name}</p>
                      <Input
                        className="mt-1"
                        placeholder="关联说明..."
                        value={
                          editingBridgeNotes.has(b.bridge_id)
                            ? editingBridgeNotes.get(b.bridge_id)!
                            : b.relevance_note || ""
                        }
                        onChange={(e) => {
                          setEditingBridgeNotes((prev) => {
                            const next = new Map(prev)
                            next.set(b.bridge_id, e.target.value)
                            return next
                          })
                        }}
                      />
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0 text-destructive hover:text-destructive"
                      onClick={() => handleRemoveBridge(b.bridge_id)}
                    >
                      移除
                    </Button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={handleSyncBridges} disabled={syncing}>
                {syncing ? "同步中..." : "同步关联"}
              </Button>
              {editingBridgeNotes.size > 0 && (
                <Button variant="outline" onClick={handleSaveBridgeNotes}>
                  保存备注
                </Button>
              )}
            </div>
            {bridgeError && <p className="text-sm text-destructive">{bridgeError}</p>}
            {bridgeSuccess && <p className="text-sm text-green-600">{bridgeSuccess}</p>}
          </CardContent>
        </Card>

        {/* Card 4: L2 Content */}
        <Card>
          <CardHeader>
            <CardTitle>L2 深挖内容</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Comparisons */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base font-medium">对比分析</Label>
                <Button variant="outline" size="sm" onClick={addComparison}>
                  添加
                </Button>
              </div>
              {(l2.comparisons || []).map((item, idx) => (
                <div key={idx} className="space-y-2 rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <Input
                      placeholder="标题"
                      value={item.title}
                      onChange={(e) => updateComparison(idx, "title", e.target.value)}
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => removeComparison(idx)}
                    >
                      删除
                    </Button>
                  </div>
                  <Textarea
                    placeholder="内容"
                    value={item.content}
                    onChange={(e) => updateComparison(idx, "content", e.target.value)}
                    rows={3}
                  />
                </div>
              ))}
            </div>

            {/* Evolution */}
            <div className="space-y-2">
              <Label className="text-base font-medium">演变脉络</Label>
              <Textarea
                placeholder="描述知识点的历史演变..."
                value={l2.evolution || ""}
                onChange={(e) => setL2((prev) => ({ ...prev, evolution: e.target.value }))}
                rows={4}
              />
            </div>

            {/* Controversies */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base font-medium">争议观点</Label>
                <Button variant="outline" size="sm" onClick={addControversy}>
                  添加
                </Button>
              </div>
              {(l2.controversies || []).map((item, idx) => (
                <div key={idx} className="space-y-2 rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <Input
                      placeholder="标题"
                      value={item.title}
                      onChange={(e) => updateControversy(idx, "title", e.target.value)}
                      className="flex-1"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => removeControversy(idx)}
                    >
                      删除
                    </Button>
                  </div>
                  <Textarea
                    placeholder="描述"
                    value={item.description}
                    onChange={(e) => updateControversy(idx, "description", e.target.value)}
                    rows={3}
                  />
                </div>
              ))}
            </div>

            {/* Further Reading */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-base font-medium">延伸阅读</Label>
                <Button variant="outline" size="sm" onClick={addFurtherReading}>
                  添加
                </Button>
              </div>
              {(l2.further_reading || []).map((item, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    placeholder="标题"
                    value={item.title}
                    onChange={(e) => updateFurtherReading(idx, e.target.value)}
                    className="flex-1"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive"
                    onClick={() => removeFurtherReading(idx)}
                  >
                    删除
                  </Button>
                </div>
              ))}
            </div>

            {l2Error && <p className="text-sm text-destructive">{l2Error}</p>}
            {l2Success && <p className="text-sm text-green-600">已保存</p>}
            <Button onClick={handleSaveL2} disabled={l2Saving}>
              {l2Saving ? "保存中..." : "保存 L2 内容"}
            </Button>
          </CardContent>
        </Card>

        {/* Card 5: Delete */}
        <Card>
          <CardHeader>
            <CardTitle>删除知识点</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              删除后相关要点和闪卡也将被移除，此操作不可撤销。
            </p>
            {deleteError && <p className="text-sm text-destructive">{deleteError}</p>}
            <Button
              variant="destructive"
              onClick={() => setIsDeleteDialogOpen(true)}
            >
              删除知识点
            </Button>
          </CardContent>
        </Card>
      </main>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除知识点「{kp.name}」吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDeleteDialogOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={isDeleting}
            >
              {isDeleting ? "删除中..." : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
