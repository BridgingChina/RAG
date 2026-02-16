import { PageHeader } from "@/components/layout/PageHeader"
import { AskPanel } from "@/components/ask/AskPanel"

export function Component() {
  return (
    <>
      <PageHeader title="问答测试" description="测试检索和生成功能" />
      <main className="p-6">
        <AskPanel />
      </main>
    </>
  )
}
