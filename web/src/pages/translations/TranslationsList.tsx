import { useCallback, useState } from "react"
import { Link } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { Pagination } from "@/components/Pagination"
import { useApi } from "@/hooks/useApi"
import {
  batchGenerateTranslations,
  fetchTranslationCoverage,
  fetchTranslations,
  reviewTranslation,
} from "@/lib/api"
import type { TranslationReviewItem, TranslationStatus } from "@/lib/types"
import { TranslationReviewDialog } from "./TranslationReviewDialog"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

// Tables that have an inline TranslationCell on their detail page — clicking
// the row deep-links there. Others fall back to the legacy modal审校 dialog
// (which can be retired once inline support is added for them).
const INLINE_SUPPORTED: Record<string, (rowId: string) => string> = {
  bridges: (rowId) => `/bridges/${rowId}`,
  knowledge_points: (rowId) => `/knowledge-points/${rowId}`,
}

function deepLinkTarget(row: TranslationReviewItem): string | null {
  const builder = INLINE_SUPPORTED[row.table_name]
  if (!builder) return null
  return `${builder(row.row_id)}?tr=${encodeURIComponent(row.field_name)}`
}

const NONE = "__all__"

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: NONE, label: "全部状态" },
  { value: "pending_ai", label: "待 AI 翻译" },
  { value: "ai_generated", label: "待人工审校" },
  { value: "human_reviewed", label: "已审校" },
  { value: "rejected", label: "已驳回" },
]

// Keep aligned with RAG/app/services/translation_service.py::TRANSLATABLE_FIELDS.
const FIELD_OPTIONS: Array<{ value: string; label: string }> = [
  { value: NONE, label: "全部字段" },
  { value: "bridges:name_en", label: "桥梁 · name" },
  { value: "bridges:description_en", label: "桥梁 · description" },
  { value: "knowledge_points:name_en", label: "知识点 · name" },
  { value: "knowledge_points:summary_en", label: "知识点 · summary" },
  { value: "flashcards:front_title_en", label: "闪卡 · front_title" },
  { value: "flashcards:back_answer_en", label: "闪卡 · back_answer" },
  { value: "taxonomy_nodes:name_en", label: "分类 · name (lvl3)" },
]

const STATUS_BADGE: Record<TranslationStatus, { variant: "default" | "secondary" | "destructive" | "outline"; label: string }> = {
  pending_ai: { variant: "outline", label: "待翻译" },
  ai_generated: { variant: "secondary", label: "待审校" },
  human_reviewed: { variant: "default", label: "已通过" },
  rejected: { variant: "destructive", label: "已驳回" },
}

function truncate(text: string, limit = 140): string {
  if (!text) return "-"
  if (text.length <= limit) return text
  return `${text.slice(0, limit)}…`
}

export function Component() {
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>("ai_generated")
  const [fieldFilter, setFieldFilter] = useState<string>(NONE)
  const [dialogItem, setDialogItem] = useState<TranslationReviewItem | null>(null)
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchError, setBatchError] = useState<string | null>(null)
  const [batchMsg, setBatchMsg] = useState<string | null>(null)
  const [approveAllOpen, setApproveAllOpen] = useState(false)
  const [approveProgress, setApproveProgress] = useState<{ done: number; total: number } | null>(null)

  const tableField = fieldFilter === NONE ? { table: undefined, field: undefined } : (() => {
    const [tbl, fld] = fieldFilter.split(":")
    return { table: tbl, field: fld }
  })()

  const { data, loading, error, refetch } = useApi(
    () =>
      fetchTranslations({
        page,
        page_size: 20,
        status: statusFilter === NONE ? undefined : statusFilter,
        table: tableField.table,
        field: tableField.field,
      }),
    [page, statusFilter, fieldFilter],
  )

  const { data: coverage } = useApi(() => fetchTranslationCoverage(), [])

  const resetPage = useCallback(<T,>(setter: (v: T) => void) => (value: T) => {
    setter(value)
    setPage(1)
  }, [])

  const handleApproveAll = useCallback(async () => {
    if (!data) return
    const targets = data.items.filter(
      (r) => r.status === "ai_generated" && r.ai_translation,
    )
    if (targets.length === 0) {
      setApproveAllOpen(false)
      return
    }
    setApproveProgress({ done: 0, total: targets.length })
    setBatchError(null)
    setBatchMsg(null)
    let ok = 0
    let failed = 0
    for (const row of targets) {
      try {
        await reviewTranslation(row.id, { action: "approve" })
        ok += 1
      } catch {
        failed += 1
      }
      setApproveProgress({ done: ok + failed, total: targets.length })
    }
    setApproveProgress(null)
    setApproveAllOpen(false)
    setBatchMsg(`批量通过：成功 ${ok} 条${failed ? `，失败 ${failed} 条` : ""}`)
    refetch()
  }, [data, refetch])

  const handleBatchGenerate = useCallback(async () => {
    if (fieldFilter === NONE) {
      setBatchError("请先选择一个字段再触发批量翻译")
      return
    }
    setBatchError(null)
    setBatchMsg(null)
    setBatchBusy(true)
    try {
      const [tbl, fld] = fieldFilter.split(":")
      const result = await batchGenerateTranslations({
        table_name: tbl,
        field_name: fld,
        limit: 100,
      })
      setBatchMsg(
        `本次翻译 ${result.started} 条，跳过 ${result.already_queued} 条，剩余待翻译 ${result.total_pending} 条`
      )
      refetch()
    } catch (e) {
      setBatchError(e instanceof Error ? e.message : String(e))
    } finally {
      setBatchBusy(false)
    }
  }, [fieldFilter, refetch])

  if (loading && !data) {
    return (
      <>
        <PageHeader title="翻译审校" description="AI 生成的英文译文管理" />
        <main className="min-w-0 space-y-6 overflow-x-hidden p-6">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-96 w-full" />
        </main>
      </>
    )
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="翻译审校" description="AI 生成的英文译文管理" />
        <main className="p-6">
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{error || "加载失败"}</p>
            <Button onClick={refetch} variant="outline" size="sm">重试</Button>
          </div>
        </main>
      </>
    )
  }

  const { items, total_pages, total } = data

  return (
    <>
      <PageHeader title="翻译审校" description="AI 生成的英文译文管理" />
      <main className="space-y-6 p-6">
        {/* Coverage summary */}
        {coverage && coverage.tables.length > 0 && (
          <div className="grid grid-cols-2 gap-2 rounded-lg border bg-muted/30 p-4 text-xs md:grid-cols-4">
            {coverage.tables.map((row) => (
              <div key={`${row.table}.${row.field}`} className="flex flex-col gap-0.5">
                <span className="text-muted-foreground">{row.table}.{row.field}</span>
                <span className="font-mono">
                  {row.translated}/{row.total} ({row.pct.toFixed(1)}%)
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Filters + batch bar */}
        <div className="flex flex-wrap items-center gap-4">
          <Select value={statusFilter} onValueChange={resetPage(setStatusFilter)}>
            <SelectTrigger className="w-[180px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={fieldFilter} onValueChange={resetPage(setFieldFilter)}>
            <SelectTrigger className="w-[240px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              {FIELD_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            disabled={batchBusy || fieldFilter === NONE}
            onClick={handleBatchGenerate}
          >
            {batchBusy ? "翻译中…" : "批量 AI 翻译（当前字段）"}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={statusFilter !== "ai_generated" || data.items.length === 0}
            onClick={() => setApproveAllOpen(true)}
            title="只作用于本页 ai_generated 状态的行"
          >
            批量通过本页
          </Button>
          <span className="ml-auto text-xs text-muted-foreground">共 {total} 条</span>
        </div>

        {(batchError || batchMsg) && (
          <div
            className={
              batchError
                ? "rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
                : "rounded-lg border border-[var(--songci-celadon)]/50 bg-[var(--songci-celadon)]/10 p-3 text-sm text-[var(--songci-celadon-deep)]"
            }
          >
            {batchError ?? batchMsg}
          </div>
        )}

        {/* Table */}
        {items.length === 0 ? (
          <div className="rounded-lg border border-dashed p-12 text-center">
            <p className="text-sm text-muted-foreground">暂无待审校记录</p>
          </div>
        ) : (
          <>
            <div className="w-full overflow-hidden rounded-lg border">
              <Table className="w-full table-fixed">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[180px]">字段</TableHead>
                    <TableHead className="w-auto">中文原文</TableHead>
                    <TableHead className="w-auto">英文译文</TableHead>
                    <TableHead className="w-[90px]">状态</TableHead>
                    <TableHead className="w-[90px] text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((row) => {
                    const badge = STATUS_BADGE[row.status]
                    const display = row.reviewed_translation ?? row.ai_translation
                    return (
                      <TableRow key={row.id}>
                        <TableCell className="truncate font-mono text-xs">
                          {row.table_name}.{row.field_name}
                        </TableCell>
                        <TableCell className="align-top text-sm">
                          <div className="line-clamp-3 break-words whitespace-normal">
                            {truncate(row.source_text)}
                          </div>
                        </TableCell>
                        <TableCell className="align-top text-sm text-muted-foreground">
                          <div className="line-clamp-3 break-words whitespace-normal">
                            {display ? truncate(display) : <em className="opacity-60">尚未生成</em>}
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge variant={badge.variant}>{badge.label}</Badge>
                        </TableCell>
                        <TableCell className="align-top text-right">
                          {(() => {
                            const target = deepLinkTarget(row)
                            return target ? (
                              <Button asChild variant="ghost" size="sm">
                                <Link to={target}>前往审校 →</Link>
                              </Button>
                            ) : (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setDialogItem(row)}
                                title="该字段尚未支持就地审校，使用弹窗"
                              >
                                审校
                              </Button>
                            )
                          })()}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>

            <Pagination page={page} totalPages={total_pages} onPageChange={setPage} />
          </>
        )}
      </main>

      <TranslationReviewDialog
        item={dialogItem}
        onClose={() => setDialogItem(null)}
        onSaved={() => {
          setDialogItem(null)
          refetch()
        }}
      />

      <Dialog open={approveAllOpen} onOpenChange={(o) => { if (!o && !approveProgress) setApproveAllOpen(false) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>批量通过本页</DialogTitle>
            <DialogDescription>
              将把本页所有 <Badge variant="secondary">待审校</Badge> 行按 AI 原译文直接通过并反写业务表。
              <br />
              <strong>此操作不可撤销。</strong>
            </DialogDescription>
          </DialogHeader>
          {approveProgress ? (
            <p className="text-sm">
              进度：{approveProgress.done} / {approveProgress.total}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              影响 {data.items.filter((r) => r.status === "ai_generated" && r.ai_translation).length} 条
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={!!approveProgress}
              onClick={() => setApproveAllOpen(false)}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              disabled={!!approveProgress}
              onClick={handleApproveAll}
            >
              {approveProgress ? "执行中…" : "确认批量通过"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
