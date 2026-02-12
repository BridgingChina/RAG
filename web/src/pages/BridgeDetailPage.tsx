import { useState } from "react"
import { useParams, useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { BridgeForm } from "@/components/bridges/BridgeForm"
import { useApi } from "@/hooks/useApi"
import {
  fetchBridge,
  updateBridge,
  deleteBridge,
  fetchBridgeChunks,
} from "@/lib/api"
import type { BridgeUpdateRequest } from "@/lib/types"

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
  const { id } = useParams()
  const navigate = useNavigate()
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const { data: bridge, loading, error, refetch } = useApi(
    () => fetchBridge(Number(id)),
    [id],
  )

  const { data: chunksData } = useApi(
    () => fetchBridgeChunks(Number(id)),
    [id],
  )

  const handleUpdate = async (data: BridgeUpdateRequest) => {
    if (!id) return
    setActionError(null)
    try {
      await updateBridge(Number(id), data)
      refetch()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
      throw e
    }
  }

  const handleDelete = async () => {
    if (!id) return
    setIsDeleting(true)
    setActionError(null)
    try {
      await deleteBridge(Number(id))
      navigate("/bridges")
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
        <PageHeader title="桥梁详情" />
        <main className="space-y-6 p-6">
          <Skeleton className="h-96 w-full" />
          <Skeleton className="h-64 w-full" />
        </main>
      </>
    )
  }

  if (error || !bridge) {
    return (
      <>
        <PageHeader title="桥梁详情" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">
              {error || "未找到桥梁"}
            </p>
            <Button onClick={() => navigate("/bridges")} variant="outline">
              返回列表
            </Button>
          </div>
        </main>
      </>
    )
  }

  const chunks = chunksData?.items || []
  const canDelete = bridge.chunk_count === 0

  return (
    <>
      <PageHeader title="桥梁详情">
        <Button onClick={() => navigate("/bridges")} variant="outline">
          返回列表
        </Button>
      </PageHeader>

      <main className="space-y-6 p-6">
        {/* Edit Form */}
        <Card>
          <CardHeader>
            <CardTitle>编辑信息</CardTitle>
          </CardHeader>
          <CardContent>
            {actionError && (
              <p className="mb-4 text-sm text-destructive">{actionError}</p>
            )}
            <BridgeForm
              initialData={bridge}
              onSubmit={handleUpdate}
              submitLabel="保存修改"
            />
          </CardContent>
        </Card>

        {/* Associated Chunks */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>关联知识块</CardTitle>
              <Badge variant="secondary">{bridge.chunk_count}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {chunks.length === 0 ? (
              <p className="text-sm text-muted-foreground">暂无关联知识块</p>
            ) : (
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>内容预览</TableHead>
                      <TableHead>分类</TableHead>
                      <TableHead>绑定状态</TableHead>
                      <TableHead>来源</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {chunks.map((chunk) => (
                      <TableRow
                        key={chunk.id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/chunks/${chunk.id}`)}
                      >
                        <TableCell className="max-w-md truncate">
                          {chunk.content_preview}
                        </TableCell>
                        <TableCell>
                          {chunk.lvl1 || (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getBindingVariant(chunk.binding_status)}>
                            {getBindingLabel(chunk.binding_status)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {chunk.source_title || (
                            <span className="text-muted-foreground">
                              未命名来源
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Delete Section */}
        <Card>
          <CardHeader>
            <CardTitle>删除桥梁</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              仅当无关联知识块时可删除
            </p>
            {actionError && !isDeleteDialogOpen && (
              <p className="text-sm text-destructive">{actionError}</p>
            )}
            <Button
              variant="destructive"
              onClick={() => setIsDeleteDialogOpen(true)}
              disabled={!canDelete}
            >
              删除桥梁
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
              确定要删除桥梁「{bridge.name}」吗？此操作不可撤销。
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
