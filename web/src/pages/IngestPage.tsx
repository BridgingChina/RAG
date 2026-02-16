import { PageHeader } from "@/components/layout/PageHeader"
import { IngestPanel } from "@/components/ingest/IngestPanel"

export function Component() {
  return (
    <>
      <PageHeader title="入库" description="上传 Markdown 文档到知识库" />
      <main className="p-6">
        <IngestPanel />
      </main>
    </>
  )
}
