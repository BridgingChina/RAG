import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
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
import { useApi } from "@/hooks/useApi"
import {
  fetchBridgeImages,
  presignBridgeImage,
  uploadFileToR2,
  confirmBridgeImage,
  deleteBridgeImage,
  reorderBridgeImages,
} from "@/lib/api"
import type { BridgeImage } from "@/lib/types"

const NONE = "__none__"

const IMAGE_TYPES: { value: string; label: string }[] = [
  { value: "photo", label: "照片" },
  { value: "illustration", label: "示意图" },
  { value: "map", label: "地图" },
]

function typeLabel(type: string | null): string {
  return IMAGE_TYPES.find((t) => t.value === type)?.label ?? "未分类"
}

interface EditState {
  image: BridgeImage
  caption: string
  type: string
}

export function BridgeImageManager({ bridgeId }: { bridgeId: string }) {
  const { data, loading, refetch } = useApi(
    () => fetchBridgeImages(bridgeId),
    [bridgeId],
  )
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [editState, setEditState] = useState<EditState | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const images = data ?? []

  const handleUpload = async (file: File) => {
    setUploading(true)
    setProgress(0)
    setError(null)
    try {
      const presign = await presignBridgeImage(bridgeId, {
        file_name: file.name,
        content_type: file.type || "image/jpeg",
      })
      await uploadFileToR2(
        presign.upload_url,
        file,
        file.type || "image/jpeg",
        setProgress,
      )
      await confirmBridgeImage(bridgeId, { image_id: presign.image_id })
      refetch()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleUpload(file)
    }
    // Reset input so re-selecting the same file works
    e.target.value = ""
  }

  const handleDelete = async (imageId: string) => {
    setError(null)
    try {
      await deleteBridgeImage(bridgeId, imageId)
      refetch()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleMoveUp = async (index: number) => {
    if (index <= 0) return
    const newOrder = [...images]
    const [item] = newOrder.splice(index, 1)
    newOrder.splice(index - 1, 0, item)
    setError(null)
    try {
      await reorderBridgeImages(
        bridgeId,
        newOrder.map((img) => img.id),
      )
      refetch()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleMoveDown = async (index: number) => {
    if (index >= images.length - 1) return
    const newOrder = [...images]
    const [item] = newOrder.splice(index, 1)
    newOrder.splice(index + 1, 0, item)
    setError(null)
    try {
      await reorderBridgeImages(
        bridgeId,
        newOrder.map((img) => img.id),
      )
      refetch()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>桥梁图片</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{images.length}</Badge>
            <Button
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? `上传中 ${progress}%` : "上传图片"}
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <p className="mb-4 text-sm text-destructive">{error}</p>
        )}

        {uploading && (
          <div className="mb-4">
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {loading && !data ? (
          <div className="grid grid-cols-3 gap-4">
            <Skeleton className="aspect-square" />
            <Skeleton className="aspect-square" />
            <Skeleton className="aspect-square" />
          </div>
        ) : images.length === 0 ? (
          <p className="text-sm text-muted-foreground">暂无图片</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            {images.map((img, index) => (
              <div
                key={img.id}
                className="group relative overflow-hidden rounded-lg border bg-muted"
              >
                <img
                  src={img.url}
                  alt={img.caption || "桥梁图片"}
                  className="aspect-square w-full cursor-pointer object-cover"
                  onClick={() =>
                    setEditState({
                      image: img,
                      caption: img.caption ?? "",
                      type: img.type ?? NONE,
                    })
                  }
                />
                <div className="absolute bottom-0 left-0 right-0 bg-black/60 p-2 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100">
                  <div className="flex items-center justify-between">
                    <span className="truncate">
                      {img.caption || typeLabel(img.type)}
                    </span>
                    <Badge variant="secondary" className="ml-1 shrink-0 text-[10px]">
                      {typeLabel(img.type)}
                    </Badge>
                  </div>
                </div>
                {/* Action buttons overlay */}
                <div className="absolute right-1 top-1 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  {index > 0 && (
                    <Button
                      size="icon"
                      variant="secondary"
                      className="h-6 w-6"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleMoveUp(index)
                      }}
                      title="上移"
                    >
                      &uarr;
                    </Button>
                  )}
                  {index < images.length - 1 && (
                    <Button
                      size="icon"
                      variant="secondary"
                      className="h-6 w-6"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleMoveDown(index)
                      }}
                      title="下移"
                    >
                      &darr;
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="destructive"
                    className="h-6 w-6"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(img.id)
                    }}
                    title="删除"
                  >
                    &times;
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>

      {/* Edit Caption/Type Dialog */}
      <Dialog
        open={editState !== null}
        onOpenChange={(open) => {
          if (!open) setEditState(null)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>图片详情</DialogTitle>
          </DialogHeader>
          {editState && (
            <div className="space-y-4">
              <img
                src={editState.image.url}
                alt={editState.caption || "桥梁图片"}
                className="max-h-64 w-full rounded-lg object-contain"
              />
              <div className="space-y-2">
                <label className="text-sm font-medium">说明</label>
                <Input
                  value={editState.caption}
                  onChange={(e) =>
                    setEditState({ ...editState, caption: e.target.value })
                  }
                  placeholder="图片说明"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">类型</label>
                <Select
                  value={editState.type}
                  onValueChange={(v) =>
                    setEditState({ ...editState, type: v })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="选择类型" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>未分类</SelectItem>
                    {IMAGE_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className="text-xs text-muted-foreground">
                图片说明和类型在上传时设定，暂不支持修改。
              </p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditState(null)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
