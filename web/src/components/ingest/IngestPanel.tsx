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
  const [bridgeCandidates, setBridgeCandidates] = useState("")
  const [minPrimaryConfidence, setMinPrimaryConfidence] = useState("0.75")
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
      const candidateList = bridgeCandidates
        .split(/[,\n，、;；|]+/)
        .map((s) => s.trim())
        .filter(Boolean)
      const confidence = Number.parseFloat(minPrimaryConfidence)
      const res = await ingestDocument(c, sourceType, {
        bridgeCandidates: candidateList.length > 0 ? candidateList : null,
        minPrimaryConfidence: Number.isNaN(confidence) ? 0.75 : confidence,
        enableAutoBridgeDetection: true,
      })
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
          placeholder={"---\nbridges:\n  - 赵州桥\n  - 卢沟桥\nsource_type: document\ntitle: 资料标题\n---\n\n# 章节标题\n\n正文内容..."}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="font-mono min-h-[300px] resize-y"
        />
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          <input
            value={bridgeCandidates}
            onChange={(e) => setBridgeCandidates(e.target.value)}
            placeholder="候选桥（可选，逗号分隔）"
            className="text-sm border border-slate-200 rounded-md px-3 py-2 text-slate-600 bg-white"
          />
          <input
            value={minPrimaryConfidence}
            onChange={(e) => setMinPrimaryConfidence(e.target.value)}
            placeholder="主桥阈值（默认0.75）"
            className="text-sm border border-slate-200 rounded-md px-3 py-2 text-slate-600 bg-white"
          />
        </div>
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
              {result.primary_bridge_names.length > 0 && (
                <h2 className="font-serif text-xl font-semibold text-slate-800">
                  主桥：{result.primary_bridge_names.join(" / ")}
                </h2>
              )}
              {result.title && (
                <p className="text-sm text-slate-400">{result.title}</p>
              )}
              <p className="text-xs text-slate-500 mt-1">
                歧义块：{result.ambiguous_chunk_count}
                {result.auto_created_bridges.length > 0
                  ? ` · 自动建桥：${result.auto_created_bridges.join("、")}`
                  : ""}
              </p>
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
