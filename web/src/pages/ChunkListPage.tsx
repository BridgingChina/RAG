import { useState } from "react"
import { PageHeader } from "@/components/layout/PageHeader"
import { ChunkFilters } from "@/components/chunks/ChunkFilters"
import { ChunkTable } from "@/components/chunks/ChunkTable"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useApi } from "@/hooks/useApi"
import { fetchChunks } from "@/lib/api"

export function Component() {
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<{
    search?: string
    lvl1?: string
    binding_status?: string
  }>({})

  const { data, loading, error, refetch } = useApi(
    () => fetchChunks({ page, page_size: 20, ...filters }),
    [page, filters],
  )

  const handleFiltersChange = (
    newFilters: typeof filters,
  ) => {
    setFilters(newFilters)
    setPage(1) // Reset to first page when filters change
  }

  return (
    <>
      <PageHeader title="知识块" description="浏览和管理知识块" />
      <main className="space-y-6 p-6">
        <ChunkFilters filters={filters} onChange={handleFiltersChange} />

        {loading && (
          <div className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6">
            <p className="mb-4 text-sm text-destructive">{error}</p>
            <Button onClick={refetch} variant="outline" size="sm">
              重试
            </Button>
          </div>
        )}

        {data && !loading && !error && (
          <>
            <ChunkTable items={data.items} />

            <div className="flex items-center justify-between gap-4">
              <p className="text-sm text-muted-foreground">
                第 {data.page} / {data.total_pages} 页
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 1}
                  onClick={() => setPage(page - 1)}
                >
                  上一页
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === data.total_pages}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </div>
          </>
        )}
      </main>
    </>
  )
}
