import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Upload, Loader2 } from "lucide-react"
import { ingestDocument } from "@/lib/api"
import type { IngestResponse } from "@/lib/types"
import { ChunkList } from "./ChunkList"

const SOURCE_TYPES = ["document", "note"]

// WARNING: This panel allows direct access to the /ingest endpoint without authentication.
// For production deployment, implement authentication and authorization checks.
// See web/SECURITY.md for details.
export function IngestPanel() {
  const [content, setContent] = useState("")
  const [sourceType, setSourceType] = useState("document")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<IngestResponse | null>(null)

  async function handleSubmit() {
    const c = content.trim()
    if (!c) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await ingestDocument(c, sourceType)
      setResult(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : "入库失败")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Input area */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-slate-700">Markdown 内容</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            className="text-sm border border-slate-200 rounded-md px-2 py-1 text-slate-600 bg-white cursor-pointer"
          >
            {SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <Textarea
          placeholder={"---\nbridge: 桥梁名称\nsource_type: document\ntitle: 资料标题\n---\n\n# 章节标题\n\n正文内容..."}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="font-mono min-h-[300px] resize-y"
        />
        <div className="flex justify-end">
          <Button
            onClick={handleSubmit}
            disabled={loading || !content.trim()}
            className="bg-orange-500 hover:bg-orange-600 text-white cursor-pointer"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            {loading ? "入库中…" : "提交入库"}
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
          <div className="flex items-baseline justify-between">
            <div>
              {result.bridge_name && (
                <h2 className="font-serif text-xl font-semibold text-slate-800">
                  {result.bridge_name}
                </h2>
              )}
              {result.title && (
                <p className="text-sm text-slate-400">{result.title}</p>
              )}
            </div>
            <span className="text-sm text-slate-500">
              共 <span className="font-semibold text-blue-500">{result.chunk_count}</span> 个知识块
            </span>
          </div>
          <ChunkList chunks={result.chunks} />
        </div>
      )}
    </div>
  )
}
