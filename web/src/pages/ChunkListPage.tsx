import { PageHeader } from "@/components/layout/PageHeader"

export function Component() {
  return (
    <>
      <PageHeader title="知识块" description="浏览和管理知识块" />
      <main className="p-6">
        <p className="text-muted-foreground">加载中...</p>
      </main>
    </>
  )
}
