import { useState, useRef } from "react"
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import {
  batchGeocode,
  importCoordinatesCsv,
  batchGenerateFlashcards,
  fetchKnowledgePoints,
  syncKPBridges,
} from "@/lib/api"

// ---------------------------------------------------------------------------
// GeocodeSection
// ---------------------------------------------------------------------------

function GeocodeSection() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ total: number; success: number; failed: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run(scope: "missing" | "all") {
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      // null = missing only (backend default), empty array would mean none
      const res = await batchGeocode(scope === "all" ? [] : undefined)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">批量地理编码</h3>
      <p className="text-sm text-muted-foreground">
        使用高德 API 批量为缺少坐标的桥梁补全经纬度
      </p>
      <div className="flex gap-2">
        <Button size="sm" disabled={loading} onClick={() => run("missing")}>
          {loading ? "处理中..." : "补全缺失坐标"}
        </Button>
        <Button size="sm" variant="outline" disabled={loading} onClick={() => run("all")}>
          全部重新编码
        </Button>
      </div>
      {result && (
        <p className="text-sm text-green-700">
          成功 {result.success} / 失败 {result.failed} / 共 {result.total}
        </p>
      )}
      {error && <p className="text-sm text-red-600">错误: {error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// FlashcardSection
// ---------------------------------------------------------------------------

function FlashcardSection() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ total_generated: number; errors: Array<{ kp_id: string; error: string }> } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      // Fetch all KP IDs (paginated, collect all pages)
      const allIds: string[] = []
      let page = 1
      while (true) {
        const resp = await fetchKnowledgePoints({ page, page_size: 100 })
        for (const item of resp.items) {
          allIds.push(item.id)
        }
        if (page * 100 >= resp.total) break
        page++
      }

      if (allIds.length === 0) {
        setError("没有找到知识点")
        return
      }

      const res = await batchGenerateFlashcards(allIds)
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">批量生成闪卡</h3>
      <p className="text-sm text-muted-foreground">
        为所有知识点批量生成闪卡（已有闪卡的知识点将跳过）
      </p>
      <Button size="sm" disabled={loading} onClick={run}>
        {loading ? "生成中..." : "为全部知识点生成"}
      </Button>
      {result && (
        <div className="space-y-1">
          <p className="text-sm text-green-700">
            成功生成 {result.total_generated} 张闪卡
          </p>
          {result.errors.length > 0 && (
            <p className="text-sm text-amber-600">
              {result.errors.length} 个知识点生成失败
            </p>
          )}
        </div>
      )}
      {error && <p className="text-sm text-red-600">错误: {error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// KPBridgeSyncSection
// ---------------------------------------------------------------------------

function KPBridgeSyncSection() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ total: number; synced: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      // Fetch all KP IDs
      const allIds: string[] = []
      let page = 1
      while (true) {
        const resp = await fetchKnowledgePoints({ page, page_size: 100 })
        for (const item of resp.items) {
          allIds.push(item.id)
        }
        if (page * 100 >= resp.total) break
        page++
      }

      if (allIds.length === 0) {
        setError("没有找到知识点")
        return
      }

      let totalSynced = 0
      for (const id of allIds) {
        const res = await syncKPBridges(id)
        totalSynced += res.synced
      }
      setResult({ total: allIds.length, synced: totalSynced })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">知识点桥梁同步</h3>
      <p className="text-sm text-muted-foreground">
        为所有知识点自动关联相关桥梁（基于 chunk 关联推断）
      </p>
      <Button size="sm" disabled={loading} onClick={run}>
        {loading ? "同步中..." : "批量同步桥梁关联"}
      </Button>
      {result && (
        <p className="text-sm text-green-700">
          处理 {result.total} 个知识点，新增 {result.synced} 条关联
        </p>
      )}
      {error && <p className="text-sm text-red-600">错误: {error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// CSVImportSection
// ---------------------------------------------------------------------------

function CSVImportSection() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ matched: number; unmatched: string[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function run() {
    if (!file) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const res = await importCoordinatesCsv(file)
      setResult(res)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ""
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-3">
      <h3 className="text-sm font-semibold">CSV 坐标导入</h3>
      <p className="text-sm text-muted-foreground">
        从 CSV 文件导入桥梁坐标（格式: name,latitude,longitude）
      </p>
      <div className="flex gap-2 items-center">
        <Input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="max-w-xs"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Button size="sm" disabled={loading || !file} onClick={run}>
          {loading ? "导入中..." : "上传导入"}
        </Button>
      </div>
      {result && (
        <div className="space-y-1">
          <p className="text-sm text-green-700">匹配 {result.matched} 座桥梁</p>
          {result.unmatched.length > 0 && (
            <p className="text-sm text-amber-600">
              未匹配: {result.unmatched.join("、")}
            </p>
          )}
        </div>
      )}
      {error && <p className="text-sm text-red-600">错误: {error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export function BatchOperationsPanel() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>批量操作</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <GeocodeSection />
        <Separator />
        <FlashcardSection />
        <Separator />
        <KPBridgeSyncSection />
        <Separator />
        <CSVImportSection />
      </CardContent>
    </Card>
  )
}
