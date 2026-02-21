import { useCallback, useState } from "react"
import { Upload, Loader2 } from "lucide-react"
import {
  presignIngestUpload,
  createIngestTask,
  uploadFileToR2,
} from "@/lib/api"
import type { IngestTaskItem } from "@/lib/types"

const ALLOWED_EXTENSIONS = [".pdf", ".md"]
const MAX_FILE_SIZE = 100 * 1024 * 1024 // 100MB

interface FileUploadZoneProps {
  onTaskCreated: (task: IngestTaskItem) => void
  onError?: (error: string) => void
}

export function FileUploadZone({ onTaskCreated, onError }: FileUploadZoneProps) {
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const getFileType = (name: string): string | null => {
    const ext = name.toLowerCase().slice(name.lastIndexOf("."))
    if (ext === ".pdf") return "pdf"
    if (ext === ".md") return "md"
    return null
  }

  const getContentType = (fileType: string): string => {
    return fileType === "pdf" ? "application/pdf" : "text/markdown"
  }

  const handleFile = useCallback(async (file: File) => {
    const fileType = getFileType(file.name)
    if (!fileType) {
      setError(`不支持的文件格式。支持: ${ALLOWED_EXTENSIONS.join(", ")}`)
      return
    }
    if (file.size > MAX_FILE_SIZE) {
      setError("文件过大，最大支持 100MB")
      return
    }

    setUploading(true)
    setProgress(0)
    setError(null)

    try {
      // 1. Get presigned URL
      const contentType = getContentType(fileType)
      const presign = await presignIngestUpload({
        file_name: file.name,
        file_type: fileType,
        file_size: file.size,
        content_type: contentType,
      })

      // 2. Upload to R2
      await uploadFileToR2(presign.upload_url, file, contentType, setProgress)

      // 3. Notify backend
      const task = await createIngestTask({
        file_name: file.name,
        file_type: fileType,
        file_size: file.size,
        r2_key: presign.r2_key,
      })

      onTaskCreated(task)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "上传失败"
      setError(msg)
      onError?.(msg)
    } finally {
      setUploading(false)
      setProgress(0)
    }
  }, [onTaskCreated, onError])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleFile(file)
    },
    [handleFile],
  )

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = "" // reset so same file can be re-selected
  }

  return (
    <div className="space-y-2">
      <label
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors ${
          dragOver
            ? "border-orange-400 bg-orange-50"
            : "border-slate-200 hover:border-slate-300 bg-white"
        }`}
      >
        <input
          type="file"
          accept=".pdf,.md"
          onChange={handleInputChange}
          className="hidden"
          disabled={uploading}
        />
        {uploading ? (
          <>
            <Loader2 className="h-8 w-8 text-orange-500 animate-spin mb-2" />
            <p className="text-sm text-slate-600">
              上传中 {progress > 0 ? `${progress}%` : ""}
            </p>
          </>
        ) : (
          <>
            <Upload className="h-8 w-8 text-slate-400 mb-2" />
            <p className="text-sm text-slate-600">
              拖拽 PDF 或 Markdown 文件到此处，或点击选择
            </p>
            <p className="text-xs text-slate-400 mt-1">
              支持 .pdf .md 格式，最大 100MB
            </p>
          </>
        )}
      </label>
      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}
    </div>
  )
}
