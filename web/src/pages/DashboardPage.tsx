import { PageHeader } from "@/components/layout/PageHeader"

export function Component() {
  return (
    <>
      <PageHeader title="仪表盘" description="系统概览" />
      <main className="p-6">
        <p className="text-muted-foreground">加载中...</p>
      </main>
    </>
  )
}
