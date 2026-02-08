import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Search, ChevronDown, Loader2 } from "lucide-react"
import { askQuestion } from "@/lib/api"
import type { AskResponse } from "@/lib/types"

export function AskPanel() {
  const [question, setQuestion] = useState("")
  const [bridgeId, setBridgeId] = useState("")
  const [showFilters, setShowFilters] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AskResponse | null>(null)

  async function handleSubmit() {
    const q = question.trim()
    if (!q) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const bid = bridgeId ? parseInt(bridgeId, 10) : undefined
      const res = await askQuestion(q, isNaN(bid as number) ? undefined : bid)
      setResult(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : "请求失败")
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="space-y-6">
      {/* Input area */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <div className="flex gap-3">
          <Input
            placeholder="输入关于桥梁的问题…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            className="flex-1"
          />
          <Button
            onClick={handleSubmit}
            disabled={loading || !question.trim()}
            className="bg-orange-500 hover:bg-orange-600 text-white cursor-pointer"
          >
            {loading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            {loading ? "检索中…" : "提问"}
          </Button>
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
        >
          <ChevronDown className={`h-3 w-3 transition-transform ${showFilters ? "rotate-180" : ""}`} />
          筛选条件
        </button>
        {showFilters && (
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500">桥梁 ID</label>
            <Input
              type="number"
              placeholder="可选"
              value={bridgeId}
              onChange={(e) => setBridgeId(e.target.value)}
              className="w-32"
            />
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 space-y-4">
          <div className="h-4 w-20 bg-slate-200 rounded animate-pulse" />
          <div className="h-7 w-3/4 bg-slate-200 rounded animate-pulse" />
          <div className="space-y-2">
            <div className="h-4 w-full bg-slate-100 rounded animate-pulse" />
            <div className="h-4 w-5/6 bg-slate-100 rounded animate-pulse" />
            <div className="h-4 w-4/6 bg-slate-100 rounded animate-pulse" />
          </div>
        </div>
      )}

      {/* Result placeholder — wired in Task 7 */}
      {result && !loading && (
        <div className="text-sm text-slate-500">
          收到回答（AnswerDisplay 待实现）: {result.summary.slice(0, 100)}…
        </div>
      )}
    </div>
  )
}
