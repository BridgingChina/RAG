import { useEffect, useState } from "react"
import { useParams, useNavigate } from "react-router"
import ReactMarkdown from "react-markdown"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { useApi } from "@/hooks/useApi"
import { fetchChunk, updateChunk, deleteChunk, fetchTaxonomyTree } from "@/lib/api"
import type { ChunkUpdateRequest } from "@/lib/types"

export function Component() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data, loading, error, refetch } = useApi(
    () => fetchChunk(id!),
    [id],
  )

  const { data: taxTree } = useApi(fetchTaxonomyTree, [])
  const lvl1Options = taxTree?.items ?? []

  const [formData, setFormData] = useState<ChunkUpdateRequest>({})

  // Initialize form when data loads
  useEffect(() => {
    if (data) {
      setFormData({
        lvl1: data.lvl1,
        lvl2: data.lvl2,
        lvl3: data.lvl3,
        bridge_id: data.bridge_id,
        binding_status: data.binding_status as
          | "none"
          | "primary"
          | "ambiguous"
          | undefined,
      })
    }
  }, [data])

  const handleSave = async () => {
    if (!id) return
    setIsSaving(true)
    setActionError(null)
    try {
      await updateChunk(id!, formData)
      refetch()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!id) return
    setIsDeleting(true)
    setActionError(null)
    try {
      await deleteChunk(id!)
      navigate("/chunks")
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
      setIsDeleteDialogOpen(false)
    } finally {
      setIsDeleting(false)
    }
  }

  if (loading) {
    return (
      <>
        <PageHeader title="知识块详情" />
        <main className="space-y-6 p-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </main>
      </>
    )
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="知识块详情" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">
              {error || "未找到知识块"}
            </p>
            <Button onClick={() => navigate("/chunks")} variant="outline">
              返回列表
            </Button>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader title="知识块详情">
        <Button onClick={() => navigate("/chunks")} variant="outline">
          返回列表
        </Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {/* Content Section */}
        <Card>
          <CardHeader>
            <CardTitle>内容</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="prose prose-sm max-w-none dark:prose-invert">
              <ReactMarkdown>{data.content}</ReactMarkdown>
            </div>

            {data.contextual_text && (
              <>
                <div className="border-t" />
                <div className="rounded-md bg-muted p-4">
                  <p className="text-xs font-medium text-muted-foreground mb-2">
                    上下文描述
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {data.contextual_text}
                  </p>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Metadata Edit Section */}
        <Card>
          <CardHeader>
            <CardTitle>元数据</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">分类 (lvl1)</label>
                <Select
                  value={formData.lvl1 || "__none__"}
                  onValueChange={(value) =>
                    setFormData({ ...formData, lvl1: value === "__none__" ? null : value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择分类" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">无</SelectItem>
                    {lvl1Options.map((item) => (
                      <SelectItem key={item.node_id} value={item.label}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">主题 (lvl2)</label>
                <Input
                  value={formData.lvl2 || ""}
                  onChange={(e) =>
                    setFormData({ ...formData, lvl2: e.target.value || null })
                  }
                  placeholder="例如: 结构体系"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">知识点 (lvl3)</label>
                <Input
                  value={formData.lvl3 || ""}
                  onChange={(e) =>
                    setFormData({ ...formData, lvl3: e.target.value || null })
                  }
                  placeholder="例如: 拱桥结构"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">绑定状态</label>
                <Select
                  value={formData.binding_status || ""}
                  onValueChange={(value) =>
                    setFormData({
                      ...formData,
                      binding_status: value
                        ? (value as "none" | "primary" | "ambiguous")
                        : undefined,
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择状态" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="primary">绑定</SelectItem>
                    <SelectItem value="ambiguous">歧义</SelectItem>
                    <SelectItem value="none">未绑定</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">桥梁</label>
              <p className="text-sm text-muted-foreground">
                {data.bridge_name || "无"}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">来源</label>
              <p className="text-sm text-muted-foreground">
                {data.source_title || "未命名来源"}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">创建时间</label>
              <p className="text-sm text-muted-foreground">
                {new Date(data.created_at).toLocaleString("zh-CN")}
              </p>
            </div>

            {actionError && (
              <p className="text-sm text-destructive">{actionError}</p>
            )}

            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? "保存中..." : "保存"}
            </Button>
          </CardContent>
        </Card>

        {/* Bridge Links Section */}
        {data.bridge_links && data.bridge_links.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>桥梁关联</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>桥梁</TableHead>
                    <TableHead>角色</TableHead>
                    <TableHead>置信度</TableHead>
                    <TableHead>方法</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.bridge_links.map((link) => (
                    <TableRow key={link.id}>
                      <TableCell>{link.bridge_name || "未命名"}</TableCell>
                      <TableCell>{link.role}</TableCell>
                      <TableCell>
                        {(link.confidence * 100).toFixed(1)}%
                      </TableCell>
                      <TableCell>{link.method}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}

        {/* Delete Section */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium">删除知识块</h3>
                <p className="text-sm text-muted-foreground">
                  此操作不可撤销，将永久删除该知识块
                </p>
              </div>
              <Button
                variant="destructive"
                onClick={() => setIsDeleteDialogOpen(true)}
              >
                删除知识块
              </Button>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Delete Confirmation Dialog */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除这个知识块吗？此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
            >
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
