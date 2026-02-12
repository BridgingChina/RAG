import { PageHeader } from "@/components/layout/PageHeader"

export function Component() {
  return (
    <>
      <PageHeader title="桥梁管理" description="浏览和管理桥梁档案" />
      <main className="p-6">
        <p className="text-muted-foreground">加载中...</p>
      </main>
    </>
  )
}
