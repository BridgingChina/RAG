import { PageHeader } from "@/components/layout/PageHeader"

export function Component() {
  return (
    <>
      <PageHeader title="入库" description="导入新资料" />
      <main className="p-6">
        <p className="text-muted-foreground">加载中...</p>
      </main>
    </>
  )
}
