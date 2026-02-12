import { PageHeader } from "@/components/layout/PageHeader"

export function Component() {
  return (
    <>
      <PageHeader title="问答测试" description="测试检索和生成功能" />
      <main className="p-6">
        <p className="text-muted-foreground">加载中...</p>
      </main>
    </>
  )
}
